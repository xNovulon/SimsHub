// Keeps the animator up to date from GitHub: the wicked_animator folder of github.com/Novulxn/Sims-Hub (main branch).
//
// Every start asks GitHub for the newest commit - one small request, given up after a few seconds (offline, GitHub
// down: the animator simply opens as it is). When there is a newer one, only the files that differ are downloaded,
// each is checked against GitHub's own hash, and only once every one of them is here are they put in place - an
// update is never half-applied by a lost connection. Files that are not on GitHub (your own) are never touched; a file
// you changed yourself is copied to the update backup before it is replaced. A new "Wicked Animator.exe" is put in
// place too (the running one is moved aside) and the app then opens again as the new version.
//
// A folder that is a git checkout of the repository is left to git (it is where the animator is worked on).
// WICKED_NO_UPDATE=1 turns updating off.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace WickedAnimator;

static class Updater
{
    const string Owner = "Novulxn", Repo = "Sims-Hub", Branch = "main", Folder = "wicked_animator/";
    // Every exe that can update itself carries this text. An exe from GitHub without it is not put in place: it could
    // never update again. (Keep it in every version.)
    const string Marker = "Novulon.WickedAnimator.AutoUpdate.v1";
    static readonly string Dir = Path.Combine(App.DataDir, "update");
    static readonly string StatePath = Path.Combine(Dir, "state.json");
    static readonly string LogPath = Path.Combine(Dir, "update.log");

    // Restart: the exe itself was replaced - open the new one. Changed: files replaced or removed.
    public record Result(bool Restart, int Changed);
    static readonly Result Nothing = new(false, 0);

    // What this folder has from GitHub: the commit, and each file's git hash (to tell your own edits apart).
    sealed class State
    {
        public string Commit { get; set; }
        public Dictionary<string, string> Files { get; set; } = new();
    }

    // The commit this folder was last updated to (short), for the splash card; null before the first update.
    public static string InstalledCommit()
    {
        var c = LoadState().Commit;
        return c != null && c.Length >= 7 ? c[..7] : null;
    }

    public static async Task<Result> Run(Action<string> status)
    {
        try
        {
            if (Environment.GetEnvironmentVariable("WICKED_NO_UPDATE") == "1") return Nothing;
            Directory.CreateDirectory(Dir);
            RemoveOldExe();
            var root = App.Root;
            if (!File.Exists(Path.Combine(root, "backend", "server.py"))) return Nothing;   // no animator folder here
            if (IsRepoCheckout(root)) { Log($"{root} is a git checkout of {Owner}/{Repo}: it is updated with git, not here"); return Nothing; }

            using var http = MakeHttp();
            status("Checking for updates...");
            var commit = await LatestCommit(http);
            var state = LoadState();
            if (commit == null || commit == state.Commit) return Nothing;

            var tree = await Tree(http, commit);
            if (tree == null) return Nothing;
            var todo = new List<(string Rel, string Sha, string Target)>();
            foreach (var (rel, sha) in tree)
            {
                var target = TargetPath(root, rel);
                if (target != null && !SameAs(target, sha)) todo.Add((rel, sha, target));
            }
            var gone = state.Files.Keys.Where(k => !tree.ContainsKey(k)).ToList();
            if (todo.Count == 0 && gone.Count == 0)
            {
                foreach (var (rel, sha) in tree) state.Files[rel] = sha;
                state.Commit = commit;
                SaveState(state);
                return Nothing;
            }

            // 1. download everything that changed into a staging folder, each file checked against its git hash
            Log($"updating {root} to {commit[..7]}: {todo.Count} file(s) to download, {gone.Count} removed");
            status(todo.Count == 1 ? "Downloading an update..." : $"Downloading an update ({todo.Count} files)...");
            var stage = Path.Combine(Dir, "staging");
            if (Directory.Exists(stage)) Directory.Delete(stage, true);
            Directory.CreateDirectory(stage);
            var self = Environment.ProcessPath;
            var staged = new Dictionary<string, string>();
            using (var gate = new SemaphoreSlim(6))
            {
                var jobs = todo.Select(async f =>
                {
                    await gate.WaitAsync();
                    try
                    {
                        var data = await Download(http, commit, Folder + f.Rel, f.Sha);
                        if (IsSelf(f.Target, self) && !HasMarker(data))
                        {
                            Log($"not replacing {f.Rel}: the one on GitHub cannot update itself (rebuild it with desktop\\build.ps1)");
                            return;
                        }
                        if (f.Rel.EndsWith(".bat", StringComparison.OrdinalIgnoreCase) || f.Rel.EndsWith(".cmd", StringComparison.OrdinalIgnoreCase))
                            data = ToCrlf(data);                  // cmd.exe misreads labels in files with bare LF line ends
                        var tmp = Path.Combine(stage, Guid.NewGuid().ToString("N"));
                        await File.WriteAllBytesAsync(tmp, data);
                        lock (staged) staged[f.Rel] = tmp;
                    }
                    finally { gate.Release(); }
                }).ToList();
                await Task.WhenAll(jobs);                          // any failed download ends the update: nothing changed yet
            }

            // 2. put them in place
            status("Installing the update...");
            var backup = Path.Combine(Dir, "backup", DateTime.Now.ToString("yyyy-MM-dd_HHmmss"));
            bool restart = false, complete = true;
            int changed = 0;
            foreach (var f in todo)
            {
                if (!staged.TryGetValue(f.Rel, out var tmp)) continue;   // the exe that was not replaced
                try
                {
                    if (File.Exists(f.Target) && Edited(f.Target, f.Rel, state)) Backup(f.Target, backup, f.Rel);
                    Directory.CreateDirectory(Path.GetDirectoryName(f.Target));
                    if (IsSelf(f.Target, self))
                    {
                        // a running program can't be overwritten, but it can be moved aside
                        File.Move(f.Target, f.Target + ".old", true);
                        restart = true;
                    }
                    File.Move(tmp, f.Target, true);
                    state.Files[f.Rel] = f.Sha;
                    changed++;
                }
                catch (Exception ex) { complete = false; Log($"could not replace {f.Rel}: {ex.Message}"); }
            }
            var replaced = todo.Select(t => t.Rel).ToHashSet();
            foreach (var (rel, sha) in tree)
                if (!replaced.Contains(rel)) state.Files[rel] = sha;   // already the same as on GitHub
            // files removed from GitHub go too - only while they are still exactly as the update left them
            foreach (var rel in gone)
            {
                try
                {
                    var target = TargetPath(root, rel);
                    if (target != null && SameAs(target, state.Files[rel])) { File.Delete(target); changed++; }
                    state.Files.Remove(rel);
                }
                catch (Exception ex) { complete = false; Log($"could not remove {rel}: {ex.Message}"); }
            }
            if (complete) state.Commit = commit;              // otherwise the next start tries again
            SaveState(state);
            try { Directory.Delete(stage, true); } catch { }
            PruneBackups();
            Log($"updated {changed} file(s){(complete ? "" : " (some could not be replaced - trying again next start)")}{(restart ? "; the app itself was updated" : "")}");
            return new Result(restart, changed);
        }
        catch (Exception ex)
        {
            Log("update skipped: " + ex.Message);
            return Nothing;
        }
    }

    // -------------------------------------------------------------- GitHub
    static HttpClient MakeHttp()
    {
        var http = new HttpClient(new SocketsHttpHandler
        {
            ConnectTimeout = TimeSpan.FromSeconds(5),
            AutomaticDecompression = DecompressionMethods.All,
        })
        { Timeout = TimeSpan.FromSeconds(60) };
        http.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("NovulonWickedAnimator", App.Version));
        return http;
    }

    // The newest commit on the branch (its full hash), or null (offline, GitHub not answering, too many checks).
    static async Task<string> LatestCommit(HttpClient http)
    {
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(6));
            using var req = new HttpRequestMessage(HttpMethod.Get, $"https://api.github.com/repos/{Owner}/{Repo}/commits/{Branch}");
            req.Headers.Accept.ParseAdd("application/vnd.github.sha");
            using var r = await http.SendAsync(req, cts.Token);
            var body = (await r.Content.ReadAsStringAsync(cts.Token)).Trim();
            if (!r.IsSuccessStatusCode) { Log($"GitHub answered {(int)r.StatusCode} to the update check"); return null; }
            return body.Length == 40 && body.All(Uri.IsHexDigit) ? body.ToLowerInvariant() : null;
        }
        catch (Exception ex) { Log("no update check (offline?): " + ex.Message); return null; }
    }

    // Every file in the animator's folder at that commit: path inside the folder -> git hash.
    static async Task<Dictionary<string, string>> Tree(HttpClient http, string commit)
    {
        using var req = new HttpRequestMessage(HttpMethod.Get, $"https://api.github.com/repos/{Owner}/{Repo}/git/trees/{commit}?recursive=1");
        req.Headers.Accept.ParseAdd("application/vnd.github+json");
        using var r = await http.SendAsync(req);
        if (!r.IsSuccessStatusCode) { Log($"GitHub answered {(int)r.StatusCode} for the file list"); return null; }
        using var j = JsonDocument.Parse(await r.Content.ReadAsStringAsync());
        if (j.RootElement.TryGetProperty("truncated", out var t) && t.ValueKind == JsonValueKind.True)
        {
            Log("GitHub's file list came back incomplete - not updating");
            return null;
        }
        var files = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var e in j.RootElement.GetProperty("tree").EnumerateArray())
        {
            var path = e.GetProperty("path").GetString();
            if (e.GetProperty("type").GetString() != "blob" || e.GetProperty("mode").GetString() == "120000") continue;   // folders, links
            if (path == null || !path.StartsWith(Folder, StringComparison.Ordinal)) continue;
            files[path[Folder.Length..]] = e.GetProperty("sha").GetString();
        }
        return files.Count > 0 ? files : null;
    }

    // One file at that commit, exactly as it is in git (checked); three tries.
    static async Task<byte[]> Download(HttpClient http, string commit, string path, string sha)
    {
        var url = $"https://raw.githubusercontent.com/{Owner}/{Repo}/{commit}/" + string.Join("/", path.Split('/').Select(Uri.EscapeDataString));
        for (int attempt = 1; ; attempt++)
        {
            try
            {
                var data = await http.GetByteArrayAsync(url);
                if (BlobSha(data) == sha) return data;
                throw new InvalidDataException("the download did not match GitHub's hash");
            }
            catch (Exception ex) when (attempt < 3)
            {
                Log($"retrying {path}: {ex.Message}");
                await Task.Delay(1000 * attempt);
            }
        }
    }

    // -------------------------------------------------------------- files
    // git's hash of a file's contents
    static string BlobSha(ReadOnlySpan<byte> data)
    {
        using var h = IncrementalHash.CreateHash(HashAlgorithmName.SHA1);
        h.AppendData(Encoding.ASCII.GetBytes($"blob {data.Length}\0"));
        h.AppendData(data);
        return Convert.ToHexString(h.GetHashAndReset()).ToLowerInvariant();
    }

    // Is the file on disk the same as that git version? Windows line ends (CRLF) count as the same text.
    static bool SameAs(string path, string sha)
    {
        if (sha == null || !File.Exists(path)) return false;
        byte[] data;
        try { data = File.ReadAllBytes(path); } catch { return false; }
        if (BlobSha(data) == sha) return true;
        if (data.AsSpan().IndexOf((byte)0) >= 0 || data.AsSpan().IndexOf("\r\n"u8) < 0) return false;   // binary, or no CRLF
        return BlobSha(FromCrlf(data)) == sha;
    }

    // Changed here since the last update (or never updated here): worth a backup before it is replaced.
    static bool Edited(string path, string rel, State state) =>
        !state.Files.TryGetValue(rel, out var had) || !SameAs(path, had);

    static byte[] FromCrlf(byte[] data)
    {
        var o = new List<byte>(data.Length);
        for (int i = 0; i < data.Length; i++)
            if (!(data[i] == '\r' && i + 1 < data.Length && data[i + 1] == '\n')) o.Add(data[i]);
        return o.ToArray();
    }

    static byte[] ToCrlf(byte[] data)
    {
        var o = new List<byte>(data.Length + data.Length / 20);
        for (int i = 0; i < data.Length; i++)
        {
            if (data[i] == '\n' && (i == 0 || data[i - 1] != '\r')) o.Add((byte)'\r');
            o.Add(data[i]);
        }
        return o.ToArray();
    }

    // Where a file of the folder goes on this PC (null for a path that would leave the folder).
    static string TargetPath(string root, string rel)
    {
        var full = Path.GetFullPath(Path.Combine(root, rel.Replace('/', Path.DirectorySeparatorChar)));
        var top = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return full.StartsWith(top, StringComparison.OrdinalIgnoreCase) ? full : null;
    }

    static bool IsSelf(string path, string self) =>
        self != null && string.Equals(Path.GetFullPath(path), Path.GetFullPath(self), StringComparison.OrdinalIgnoreCase);

    static bool HasMarker(byte[] exe) => exe.AsSpan().IndexOf(Encoding.Unicode.GetBytes(Marker)) >= 0;

    static void Backup(string path, string backup, string rel)
    {
        var to = Path.Combine(backup, rel.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(Path.GetDirectoryName(to));
        File.Copy(path, to, true);
    }

    // the three newest backups are kept
    static void PruneBackups()
    {
        try
        {
            var dir = new DirectoryInfo(Path.Combine(Dir, "backup"));
            if (!dir.Exists) return;
            foreach (var old in dir.GetDirectories().OrderByDescending(d => d.Name).Skip(3))
                try { old.Delete(true); } catch { }
        }
        catch { }
    }

    // the exe moved aside by the last update (it could not be removed while it ran)
    static void RemoveOldExe()
    {
        try { var p = Environment.ProcessPath; if (p != null && File.Exists(p + ".old")) File.Delete(p + ".old"); } catch { }
    }

    // A git checkout of this repository (a .git folder here or above, pointing at it)
    static bool IsRepoCheckout(string root)
    {
        for (var d = new DirectoryInfo(root); d != null; d = d.Parent)
        {
            var config = Path.Combine(d.FullName, ".git", "config");
            if (File.Exists(config))
            {
                try { return File.ReadAllText(config).Contains($"{Owner}/{Repo}", StringComparison.OrdinalIgnoreCase); }
                catch { return true; }
            }
        }
        return false;
    }

    static State LoadState()
    {
        try { return JsonSerializer.Deserialize<State>(File.ReadAllText(StatePath)) ?? new State(); }
        catch { return new State(); }
    }

    static void SaveState(State state)
    {
        var tmp = StatePath + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(state, new JsonSerializerOptions { WriteIndented = true }));
        File.Move(tmp, StatePath, true);
    }

    static void Log(string line)
    {
        try
        {
            Directory.CreateDirectory(Dir);
            var fi = new FileInfo(LogPath);
            if (fi.Exists && fi.Length > 500_000) File.Move(LogPath, LogPath + ".old", true);
            File.AppendAllText(LogPath, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {line}\n");
        }
        catch { }
    }
}
