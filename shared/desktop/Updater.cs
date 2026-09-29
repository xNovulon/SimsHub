// Keeps an app up to date from GitHub (github.com/xNovulon/SimsHub, main branch) - and installs it: an empty folder
// is simply "very out of date".
//
// 1. The app's files: every start asks GitHub for the newest commit - one small request, given up after a few seconds
//    (offline, GitHub down: the app opens as it is). When there is a newer one, only the files of the app's folder that
//    differ are downloaded, each is checked against GitHub's own hash, and only once every one of them is here are they
//    put in place - an update is never half-applied by a lost connection. Files that are not on GitHub (your own,
//    caches, logs) are never touched; a file you changed yourself is copied to the update backup before it is
//    replaced. Windows line ends (CRLF) count as the same text. Files only developers need (Brand.Skip) are left out.
// 2. The program itself: a plain folder (Brand.ProgramFolder) - the program's own files next to Microsoft's .NET,
//    never packed into one file. The "apps" release on GitHub holds the newest build of each app as a zip of that
//    folder, with <name>.build next to it (the build's id and the zip's SHA-256). When this program is a different
//    build, the zip is downloaded, checked and unpacked, and the new folder takes this one's place - the app then
//    opens again as it.
//
// A folder that is a git checkout of the repository is left to git (it is where the apps are worked on).
// WICKED_NO_UPDATE=1 / SIMS_HUB_NO_UPDATE=1 turn updating off; NOVULON_UPDATE_BRANCH picks another branch (testing).
// The Hub's Python launcher does step 1 the same way (sims_hub/speedkit/hub/update.py).
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
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
    const string Owner = "xNovulon", Repo = "SimsHub", ReleaseTag = "apps";
    static string Branch => Environment.GetEnvironmentVariable("NOVULON_UPDATE_BRANCH") is { Length: > 0 } b ? b : "main";
    static Brand B => Brand.Current;
    static string Dir => Path.Combine(B.DataDir, "update");
    static string StatePath => Path.Combine(Dir, "state.json");
    static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true, WriteIndented = true,
    };

    // Staged: a new program is ready there - open it, and it puts its folder in place (Setup.FinishUpdate).
    // Changed: files replaced or removed.
    public record Result(string Staged, int Changed);
    static readonly Result Nothing = new(null, 0);

    // Where a new program's folder waits until the running one has ended (a running program's files can't be replaced)
    public static string StagedDir => Path.Combine(Dir, "program_new");

    // What the folder has from GitHub: the commit, and each file's git hash (to tell your own edits apart)
    sealed class State
    {
        public string Commit { get; set; }
        public Dictionary<string, string> Files { get; set; } = new();
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
            CleanUp(root);
            using var http = Ui.Web(TimeSpan.FromSeconds(60));
            status("Checking for updates...");
            var commit = await LatestCommit(http);
            var state = LoadState();
            int changed = 0;
            if (commit != null && commit != state.Commit)
                changed = await Files(http, root, commit, state, status);
            var staged = program ? await Program(http, root, status) : null;
            return new Result(staged, changed);
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
        void Say() => status("Updating...");
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
        status("Updating...");
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
    // The published build, when this program is a different one: its zip downloaded, checked and unpacked into
    // StagedDir. -> the new program there, or null.
    static async Task<string> Program(HttpClient http, string root, Action<string> status)
    {
        var self = Environment.ProcessPath;
        if (self == null || !SamePath(self, B.ProgramExe(root))) return null;    // e.g. a developer's build folder
        var own = OwnBuild();
        if (own == null) return null;                                             // a build made on this PC
        var pub = await Published(http);
        if (pub == null || pub.Value.Build == own) return null;                   // offline, none published yet, or this one

        Log($"a new {B.ExeName} is published ({pub.Value.Build[..12]})");
        var zip = Path.Combine(Dir, "new.zip");
        try
        {
            status("Updating...");
            await Ui.Download(http, ReleaseUrl(B.ReleaseName + ".zip"), zip);
            string got;
            using (var f = File.OpenRead(zip)) got = Convert.ToHexString(SHA256.HashData(f)).ToLowerInvariant();
            if (got != pub.Value.Zip) { Log($"the downloaded {B.ReleaseName}.zip is not the published one yet ({got[..12]}) - next start"); return null; }
            if (Directory.Exists(StagedDir)) Directory.Delete(StagedDir, true);
            ZipFile.ExtractToDirectory(zip, StagedDir);
            var exe = Path.Combine(StagedDir, B.ExeName);
            if (BuildOf(StagedDir) != pub.Value.Build || !File.Exists(exe)
                || File.ReadAllBytes(exe).AsSpan().IndexOf(Encoding.Unicode.GetBytes(B.Marker)) < 0)
            {
                Log($"not replacing {B.ExeName}: the published one is incomplete or cannot update itself");
                Directory.Delete(StagedDir, true);
                return null;
            }
            Log($"the new {B.ExeName} is ready; it goes in place once this one has ended");
            return exe;
        }
        catch (Exception ex)
        {
            Log($"could not update {B.ExeName}: {ex.Message}");
            try { if (Directory.Exists(StagedDir)) Directory.Delete(StagedDir, true); } catch { }
            return null;
        }
        finally { try { File.Delete(zip); } catch { } }
    }

    static string ReleaseUrl(string asset) => $"https://github.com/{Owner}/{Repo}/releases/download/{ReleaseTag}/{asset}";

    // The newest published build of this app: its id and the zip's SHA-256 (lower-case hex, the two lines of
    // <name>.build), or null (offline, none published yet).
    public static async Task<(string Build, string Zip)?> Published(HttpClient http)
    {
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(8));
            var lines = (await http.GetStringAsync(ReleaseUrl(B.ReleaseName + ".build"), cts.Token))
                .Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            if (lines.Length >= 2 && Hex64(lines[0]) && Hex64(lines[1])) return (lines[0].ToLowerInvariant(), lines[1].ToLowerInvariant());
            Log("the published build is not readable");
        }
        catch (Exception ex) { Log("no published build found: " + ex.Message); }
        return null;
    }

    static bool Hex64(string s) => s.Length == 64 && s.All(Uri.IsHexDigit);

    // build.txt in a program's folder: the build's id, then every file of the build (made when it is published).
    // -> the files, or null (a build made on this PC has none).
    public static string[] Manifest(string dir)
    {
        try
        {
            var lines = File.ReadAllLines(Path.Combine(dir, "build.txt")).Select(l => l.Trim()).Where(l => l.Length > 0).ToArray();
            return lines.Length >= 2 && Hex64(lines[0]) ? lines : null;
        }
        catch { return null; }
    }

    // the build id of the program in a folder, or null
    public static string BuildOf(string dir) => Manifest(dir)?[0].ToLowerInvariant();

    public static string OwnBuild() => BuildOf(AppContext.BaseDirectory);

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

    // What updates left behind: the program's folder moved aside, a new one already in place, and the single-file
    // program (and its ".old") that versions before the program's folder kept in the app's folder.
    static void CleanUp(string root)
    {
        var self = Path.GetFullPath(AppContext.BaseDirectory);
        var old = Path.Combine(root, Brand.ProgramFolder + ".old");
        try { if (Directory.Exists(old)) Directory.Delete(old, true); } catch { }
        try
        {
            if (Directory.Exists(StagedDir) && !self.StartsWith(Path.GetFullPath(StagedDir), StringComparison.OrdinalIgnoreCase))
                Directory.Delete(StagedDir, true);
        }
        catch { }
        foreach (var legacy in new[] { Path.Combine(root, B.ExeName), Path.Combine(root, B.ExeName + ".old") })
            try { if (File.Exists(legacy) && !SamePath(legacy, Environment.ProcessPath ?? "")) File.Delete(legacy); } catch { }
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

    public static void Log(string line) => Ui.Log(Path.Combine("update", "update.log"), line);
}
