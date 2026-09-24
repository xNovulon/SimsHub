// Keeps an app up to date from GitHub (github.com/Novulxn/Sims-Hub, main branch) - and installs it: an empty folder
// is simply "very out of date".
//
// 1. The app's files: every start asks GitHub for the newest commit - one small request, given up after a few seconds
//    (offline, GitHub down: the app opens as it is). When there is a newer one, only the files of the app's folder that
//    differ are downloaded, each is checked against GitHub's own hash, and only once every one of them is here are they
//    put in place - an update is never half-applied by a lost connection. Files that are not on GitHub (your own,
//    caches, logs) are never touched; a file you changed yourself is copied to the update backup before it is
//    replaced. Windows line ends (CRLF) count as the same text. Files only developers need (Brand.Skip) are left out.
// 2. The program itself: the "apps" release on GitHub holds the newest build of each app, with its checksum next to
//    it (<asset>.sha256). When this program is a different build, the new one is downloaded, checked, and swapped in -
//    the app then opens again as it.
//
// A folder that is a git checkout of the repository is left to git (it is where the apps are worked on).
// WICKED_NO_UPDATE=1 / SIMS_HUB_NO_UPDATE=1 turn updating off; NOVULON_UPDATE_BRANCH picks another branch (testing).
// The Hub's Python launcher does step 1 the same way (sims_hub/speedkit/hub/update.py).
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Novulon.Desktop;

public static class Updater
{
    const string Owner = "Novulxn", Repo = "Sims-Hub", ReleaseTag = "apps";
    static string Branch => Environment.GetEnvironmentVariable("NOVULON_UPDATE_BRANCH") is { Length: > 0 } b ? b : "main";
    static Brand B => Brand.Current;
    static string Dir => Path.Combine(B.DataDir, "update");
    static string StatePath => Path.Combine(Dir, "state.json");
    static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true, WriteIndented = true,
    };

    // Restart: the program itself was replaced - open the new one. Changed: files replaced or removed.
    public record Result(bool Restart, int Changed);
    static readonly Result Nothing = new(false, 0);

    // What the folder has from GitHub: the commit, each file's git hash (to tell your own edits apart), and the
    // program's hash (size|time|sha256, so it is only worked out again when the program changes).
    sealed class State
    {
        public string Commit { get; set; }
        public Dictionary<string, string> Files { get; set; } = new();
        public string Exe { get; set; }
    }

    // The commit the app's folder was last updated to (short), for the splash card; null before the first update.
    public static string InstalledCommit()
    {
        var c = LoadState().Commit;
        return c != null && c.Length >= 7 ? c[..7] : null;
    }

    public static bool Disabled(string root) =>
        Environment.GetEnvironmentVariable("WICKED_NO_UPDATE") == "1" || Environment.GetEnvironmentVariable("SIMS_HUB_NO_UPDATE") == "1"
        || IsRepoCheckout(root);

    // Brings `root` up to date (an empty or missing folder: installs the app there). program: also update the running
    // program from the release (not while installing - the program doing the install copies itself).
    public static async Task<Result> Run(string root, Action<string> status, bool program = true)
    {
        try
        {
            if (Disabled(root)) { Log($"{root} is a git checkout of {Owner}/{Repo}, or updating is off: not updated here"); return Nothing; }
            Directory.CreateDirectory(Dir);
            RemoveOldExe();
            using var http = Ui.Web(TimeSpan.FromSeconds(60));
            status("Checking for updates...");
            var commit = await LatestCommit(http);
            var state = LoadState();
            int changed = 0;
            if (commit != null && commit != state.Commit)
                changed = await Files(http, root, commit, state, status);
            bool restart = program && await Program(http, root, state, status);
            return new Result(restart, changed);
        }
        catch (Exception ex)
        {
            Log("update skipped: " + ex.Message);
            return Nothing;
        }
    }

    // -------------------------------------------------------------- 1. the app's files
    static async Task<int> Files(HttpClient http, string root, string commit, State state, Action<string> status)
    {
        var all = await Tree(http, commit);
        if (all == null) return 0;
        var tree = all.Where(f => B.Wanted(f.Key)).ToDictionary(f => f.Key, f => f.Value);
        // files developers only need are not ours to keep up to date (a copy already here stays as it is)
        foreach (var rel in state.Files.Keys.Where(k => all.ContainsKey(k) && !tree.ContainsKey(k)).ToList()) state.Files.Remove(rel);
        var todo = new List<(string Rel, string Sha, string Target)>();
        foreach (var (rel, sha) in tree)
        {
            var target = TargetPath(root, rel);
            if (target != null && !SameAs(target, sha)) todo.Add((rel, sha, target));
        }
        var gone = state.Files.Keys.Where(k => !all.ContainsKey(k)).ToList();
        if (todo.Count == 0 && gone.Count == 0)
        {
            foreach (var (rel, sha) in tree) state.Files[rel] = sha;
            state.Commit = commit;
            SaveState(state);
            return 0;
        }

        // download everything that changed into a staging folder, each file checked against its git hash
        Log($"updating {root} to {commit[..7]}: {todo.Count} file(s) to download, {gone.Count} removed");
        var stage = Path.Combine(Dir, "staging");
        if (Directory.Exists(stage)) Directory.Delete(stage, true);
        Directory.CreateDirectory(stage);
        var staged = new Dictionary<string, string>();
        int done = 0;
        void Say() => status(todo.Count == 1 ? "Downloading an update..." : $"Downloading ({done} of {todo.Count} files)...");
        Say();
        using (var gate = new SemaphoreSlim(8))
        {
            var jobs = todo.Select(async f =>
            {
                await gate.WaitAsync();
                try
                {
                    var data = await Download(http, commit, B.RepoFolder + f.Rel, f.Sha);
                    if (f.Rel.EndsWith(".bat", StringComparison.OrdinalIgnoreCase) || f.Rel.EndsWith(".cmd", StringComparison.OrdinalIgnoreCase))
                        data = ToCrlf(data);                  // cmd.exe misreads labels in files with bare LF line ends
                    var tmp = Path.Combine(stage, Guid.NewGuid().ToString("N"));
                    await File.WriteAllBytesAsync(tmp, data);
                    lock (staged) { staged[f.Rel] = tmp; done++; }
                    Say();
                }
                finally { gate.Release(); }
            }).ToList();
            await Task.WhenAll(jobs);                          // any failed download ends the update: nothing changed yet
        }

        // put them in place
        status("Putting the new files in place...");
        var backup = Path.Combine(Dir, "backup", DateTime.Now.ToString("yyyy-MM-dd_HHmmss"));
        bool complete = true;
        int changed = 0;
        foreach (var f in todo)
        {
            try
            {
                if (File.Exists(f.Target) && Edited(f.Target, f.Rel, state)) Backup(f.Target, backup, f.Rel);
                Directory.CreateDirectory(Path.GetDirectoryName(f.Target));
                File.Move(staged[f.Rel], f.Target, true);
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
        Log($"updated {changed} file(s){(complete ? "" : " (some could not be replaced - trying again next start)")}");
        return changed;
    }

    // -------------------------------------------------------------- 2. the program
    // The published build, when this program is a different one: downloaded, checked, swapped in.
    static async Task<bool> Program(HttpClient http, string root, State state, Action<string> status)
    {
        var self = Environment.ProcessPath;
        var installed = Path.Combine(root, B.ExeName);
        if (self == null || !SamePath(self, installed)) return false;   // e.g. a developer's build folder
        var want = await PublishedSha(http);
        if (want == null || want == ExeSha(self, state)) return false;  // offline, none published yet, or this one

        Log($"a new {B.ExeName} is published ({want[..12]})");
        var tmp = Path.Combine(Dir, "new.exe");
        var url = ReleaseUrl(B.ReleaseAsset);
        try
        {
            status("Downloading the new version...");
            await Ui.Download(http, url, tmp, p => status($"Downloading the new version ({p:P0})..."));
            var data = await File.ReadAllBytesAsync(tmp);
            var got = Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant();
            if (got != want) { Log($"the downloaded {B.ReleaseAsset} is not the published one yet ({got[..12]}) - next start"); return false; }
            if (data.AsSpan().IndexOf(Encoding.Unicode.GetBytes(B.Marker)) < 0)
            {
                Log($"not replacing {B.ExeName}: the published one cannot update itself");
                return false;
            }
            File.Move(self, self + ".old", true);               // a running program can't be overwritten, but can be moved aside
            File.Move(tmp, self, true);
            Log($"{B.ExeName} updated");
            return true;
        }
        catch (Exception ex)
        {
            Log($"could not update {B.ExeName}: {ex.Message}");
            if (!File.Exists(self) && File.Exists(self + ".old")) File.Move(self + ".old", self);   // put it back
            return false;
        }
        finally { try { File.Delete(tmp); } catch { } }
    }

    static string ReleaseUrl(string asset) => $"https://github.com/{Owner}/{Repo}/releases/download/{ReleaseTag}/{asset}";

    // The SHA-256 of the newest published build of this app (lower-case hex), or null (offline, none published yet).
    public static async Task<string> PublishedSha(HttpClient http)
    {
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(8));
            var text = (await http.GetStringAsync(ReleaseUrl(B.ReleaseAsset + ".sha256"), cts.Token)).Trim().ToLowerInvariant();
            if (text.Length >= 64 && text[..64].All(Uri.IsHexDigit)) return text[..64];
            Log("the published checksum is not one");
        }
        catch (Exception ex) { Log("no published build found: " + ex.Message); }
        return null;
    }

    static string ExeSha(string path, State state)
    {
        var fi = new FileInfo(path);
        var key = $"{fi.Length}|{fi.LastWriteTimeUtc.Ticks}|";
        if (state.Exe != null && state.Exe.StartsWith(key)) return state.Exe[key.Length..];
        using var f = File.OpenRead(path);
        var sha = Convert.ToHexString(SHA256.HashData(f)).ToLowerInvariant();
        state.Exe = key + sha;
        try { SaveState(state); } catch { }
        return sha;
    }

    // -------------------------------------------------------------- GitHub
    // The newest commit on the branch (its full hash), or null (offline, GitHub not answering, too many checks).
    static async Task<string> LatestCommit(HttpClient http)
    {
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(8));
            using var req = new HttpRequestMessage(HttpMethod.Get, $"https://api.github.com/repos/{Owner}/{Repo}/commits/{Branch}");
            req.Headers.Accept.ParseAdd("application/vnd.github.sha");
            using var r = await http.SendAsync(req, cts.Token);
            var body = (await r.Content.ReadAsStringAsync(cts.Token)).Trim();
            if (!r.IsSuccessStatusCode) { Log($"GitHub answered {(int)r.StatusCode} to the update check"); return null; }
            return body.Length == 40 && body.All(Uri.IsHexDigit) ? body.ToLowerInvariant() : null;
        }
        catch (Exception ex) { Log("no update check (offline?): " + ex.Message); return null; }
    }

    // Every file in the app's folder at that commit: path inside the folder -> git hash.
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
            if (path == null || !path.StartsWith(B.RepoFolder, StringComparison.Ordinal)) continue;
            files[path[B.RepoFolder.Length..]] = e.GetProperty("sha").GetString();
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

    public static bool SamePath(string a, string b) =>
        string.Equals(Path.GetFullPath(a), Path.GetFullPath(b), StringComparison.OrdinalIgnoreCase);

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

    // the program moved aside by the last update (it could not be removed while it ran)
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
        try { return JsonSerializer.Deserialize<State>(File.ReadAllText(StatePath), Json) ?? new State(); }
        catch { return new State(); }
    }

    static void SaveState(State state)
    {
        Directory.CreateDirectory(Dir);
        var tmp = StatePath + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(state, Json));
        File.Move(tmp, StatePath, true);
    }

    static void Log(string line) => Ui.Log(Path.Combine("update", "update.log"), line);
}
