// Gets an app ready to open. The program's folder is all anyone downloads (a zip):
//   - opened from its app folder (the usual case: <app folder>\program): the folder is brought up to date (Updater.cs);
//   - opened from anywhere else (the unpacked download): the app is installed in its usual place (Brand.InstallDir) -
//     or that copy brought up to date - with Desktop and Start Menu shortcuts, and that copy is opened instead.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Novulon.Desktop;

public static class Setup
{
    // Root: the app's folder. Launch: start this program instead once this one has ended (see RunLaunch), with
    // LaunchArgs in front of this program's own. Failed: the app can't open (the user was told why).
    public record Ready(string Root, string Launch, bool Failed, string[] LaunchArgs = null);

    const string FinishArg = "--finish-update";
    static string _launch;
    static string[] _launchArgs = Array.Empty<string>();
    static string LogFile => Path.Combine(Brand.Current.DataDir, "setup.log");

    // The app's folder this program belongs to: the folder it is in, or one above it (a developer's build folder).
    // null: opened from somewhere else, e.g. Downloads.
    public static string FindRoot()
    {
        foreach (var start in new[] { AppContext.BaseDirectory, Path.GetDirectoryName(Environment.ProcessPath ?? "") ?? "" })
        {
            var d = new DirectoryInfo(start);
            for (int i = 0; d != null && i < 5; i++, d = d.Parent)
                if (Brand.Current.IsAppFolder(d.FullName)) return d.FullName;
        }
        return null;
    }

    public static async Task<Ready> Prepare(Action<string> status)
    {
        var b = Brand.Current;
        var root = FindRoot();
        if (root != null)
        {
            var up = await Task.Run(() => Updater.Run(root, status));
            b.Commit = Updater.InstalledCommit();
            // a new program: it takes this one's place once this one has ended, then opens
            if (up.Staged != null)
                return new Ready(root, up.Staged, false, new[] { FinishArg, Environment.ProcessPath, Environment.ProcessId.ToString() });
            return new Ready(root, null, false);
        }

        // opened from a download: install (or update) the app in its usual place, then open that copy
        var target = b.InstallDir;
        bool fresh = !b.IsAppFolder(target);
        Ui.Log("setup.log", $"{(fresh ? "installing" : "updating")} {b.Name} in {target} (opened from {Environment.ProcessPath})");
        status(fresh ? "Installing..." : "Updating...");
        await Task.Run(() => Updater.Run(target, status, program: false));
        if (!b.IsAppFolder(target))
        {
            Ui.Fatal("The app could not be installed",
                "Its files are downloaded from GitHub the first time, so this needs an internet connection. Check it, then open the app again.",
                Path.Combine(b.DataDir, "update", "update.log"));
            return new Ready(null, null, true);
        }
        var exe = b.ProgramExe(target);
        try
        {
            if (await ShouldPlaceSelf(exe)) await Task.Run(() => PlaceSelf(Path.GetDirectoryName(exe)));
        }
        catch (Exception ex)
        {
            Ui.Log("setup.log", "could not put the program in place: " + ex.Message);
            if (!File.Exists(exe))
            {
                Ui.Fatal("The app could not be installed", $"The program could not be copied to {target}.\n\n{ex.Message}", LogFile);
                return new Ready(null, null, true);
            }
        }
        MakeShortcuts(exe, target);
        return new Ready(target, exe, false);
    }

    // After this program has ended (and let go of the app's single-instance lock): open the program Prepare named.
    public static void SetLaunch(Ready ready)
    {
        _launch = ready.Launch;
        _launchArgs = ready.LaunchArgs ?? Array.Empty<string>();
    }

    public static void RunLaunch(string[] args)
    {
        if (_launch == null) return;
        try
        {
            var psi = new ProcessStartInfo(_launch) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(_launch) };
            foreach (var a in _launchArgs) psi.ArgumentList.Add(a);
            foreach (var a in args) psi.ArgumentList.Add(a);
            Process.Start(psi);
        }
        catch (Exception ex) { Ui.Fatal("The app was updated", "Open it again to use the new version.\n\n" + ex.Message); }
    }

    // The first thing Main does. Opened as "<new program> --finish-update <app's program> <pid> [args]" by the program
    // it replaces: waits for that one to end, puts its own folder in the place of that one's, opens it there and ends.
    // -> true: Main returns. It holds the app's lock (mutexName) while it works, so opening the app meanwhile can't
    // start a copy from the folder being replaced.
    public static bool FinishUpdate(string[] args, string mutexName)
    {
        if (args.Length < 3 || args[0] != FinishArg) return false;
        var target = args[1];
        var rest = args.Skip(3).ToArray();
        var run = target;                                 // what is opened at the end
        // (a handle on the lock alone makes a copy opened meanwhile step back; it is closed before the app opens)
        var lockApp = new Mutex(false, mutexName);
        bool locked = false;
        try
        {
            // 1. the old program ends (it lets go of the lock first, just before it opens this one)
            if (!WaitForExit(args[2], TimeSpan.FromMinutes(2)))
            {
                Updater.Log($"the old {Brand.Current.ExeName} did not end: the update waits for the next start");
                return true;
            }
            try { locked = lockApp.WaitOne(TimeSpan.FromSeconds(30)); }
            catch (AbandonedMutexException) { locked = true; }
            if (!locked)
            {
                // the app was opened again meanwhile: that copy updates itself next time
                Updater.Log($"{Brand.Current.ExeName} was opened meanwhile: the update waits for the next start");
                return true;
            }
            // 2. the new folder takes the old one's place (SwapIn)
            var dir = Path.GetDirectoryName(target);
            if (SwapIn(AppContext.BaseDirectory, dir, out var err)) Updater.Log($"{Brand.Current.ExeName} updated");
            else Updater.Log($"could not put the new {Brand.Current.ExeName} in place: {err?.Message}");
            // never nothing to open: the old program, wherever it is now
            var aside = Path.Combine(dir + ".old", Path.GetFileName(target));
            if (!File.Exists(target) && File.Exists(aside)) run = aside;
        }
        catch (Exception ex) { Updater.Log("update not finished: " + ex.Message); }
        finally
        {
            if (locked) try { lockApp.ReleaseMutex(); } catch { }
            lockApp.Dispose();
        }
        try
        {
            var psi = new ProcessStartInfo(run) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(run) };
            foreach (var a in rest) psi.ArgumentList.Add(a);
            Process.Start(psi);
        }
        catch (Exception ex) { Ui.Fatal("The app was updated", "Open it again to use the new version.\n\n" + ex.Message); }
        return true;
    }

    // Puts the program folder `from` in the place of `dir`: copied next to it first (<dir>.new), so `dir` is only
    // touched once the copy is complete; the old one is moved aside (<dir>.old, removed now or on a later start) and
    // comes back if anything goes wrong. Only the build's own files are copied (build.txt lists them), so an unpacked
    // download never brings along whatever else was next to it.
    static bool SwapIn(string from, string dir, out Exception err)
    {
        err = null;
        var files = Updater.Manifest(from);
        if (files == null) { err = new InvalidDataException("the program has no list of its files (build.txt)"); return false; }
        var fresh = dir + ".new";
        var old = dir + ".old";
        try { if (Directory.Exists(old)) Directory.Delete(old, true); } catch { }
        bool placed = Retry(() => CopyBuild(from, fresh, files.Skip(1).Append("build.txt")), out err)
            && Retry(() => { if (Directory.Exists(dir)) Directory.Move(dir, old); }, out err)
            && Retry(() => Directory.Move(fresh, dir), out err);
        if (!placed)
        {
            if (!Directory.Exists(dir) && Directory.Exists(old)) Retry(() => Directory.Move(old, dir), out _);
            try { Directory.Delete(fresh, true); } catch { }
            return false;
        }
        try { Directory.Delete(old, true); } catch { }      // still in use: Updater.CleanUp removes it later
        return true;
    }

    // The listed files of a build, copied as plain bytes (so the copies don't carry the download's "from the internet"
    // mark) into a fresh folder.
    static void CopyBuild(string from, string to, IEnumerable<string> files)
    {
        if (Directory.Exists(to)) Directory.Delete(to, true);
        var top = Path.GetFullPath(to).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        foreach (var rel in files)
        {
            var dst = Path.GetFullPath(Path.Combine(to, rel));
            if (!dst.StartsWith(top, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("a file outside the program: " + rel);
            Directory.CreateDirectory(Path.GetDirectoryName(dst));
            using var a = File.OpenRead(Path.Combine(from, rel));
            using var b = File.Create(dst);
            a.CopyTo(b);
        }
    }

    // true once the process has ended (or was never there)
    static bool WaitForExit(string pid, TimeSpan limit)
    {
        try
        {
            using var old = Process.GetProcessById(int.Parse(pid));
            return old.WaitForExit((int)limit.TotalMilliseconds);
        }
        catch (ArgumentException) { return true; }        // already ended
        catch (FormatException) { return true; }
    }

    // a file step, tried for up to 10 s (a program still closing, or a virus scanner looking at the new file)
    static bool Retry(Action step, out Exception error)
    {
        error = null;
        for (int i = 0; i < 40; i++)
        {
            try { step(); error = null; return true; }
            catch (Exception ex) { error = ex; Thread.Sleep(250); }
        }
        return false;
    }

    // Another copy holds the app's lock. A copy that started before this program's file was written is an old
    // program that replaced its own file in an update and could not go on (the updater before this one did that):
    // it is ended, so the app opens. -> true when one was ended.
    public static bool EndStaleCopy()
    {
        try
        {
            var self = Environment.ProcessPath;
            if (self == null) return false;
            var written = File.GetLastWriteTime(self);
            bool ended = false;
            foreach (var p in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(self)))
            {
                using (p)
                {
                    try
                    {
                        if (p.Id == Environment.ProcessId || p.StartTime >= written) continue;
                        if (!Updater.SamePath(p.MainModule?.FileName ?? "", self)) continue;
                        var started = p.StartTime;
                        p.Kill();
                        p.WaitForExit(5000);
                        ended = true;
                        Ui.Log("setup.log", $"ended an old copy left from an update (started {started:HH:mm:ss})");
                    }
                    catch { /* not ours to end, or already gone */ }
                }
            }
            return ended;
        }
        catch { return false; }
    }

    // This program goes into the app's folder when there is none there yet, or when it is the newest published build
    // and the one there is not. Otherwise the one there stays: it updates itself when it opens.
    static async Task<bool> ShouldPlaceSelf(string exe)
    {
        var self = Environment.ProcessPath;
        if (self == null || Updater.SamePath(self, exe)) return false;
        if (!File.Exists(exe)) return true;
        var own = Updater.OwnBuild();
        if (own == null || own == Updater.BuildOf(Path.GetDirectoryName(exe))) return false;
        using var http = Ui.Web(TimeSpan.FromSeconds(30));
        var pub = await Updater.Published(http);
        return pub != null && pub.Value.Build == own;
    }

    static void PlaceSelf(string dir)
    {
        if (!SwapIn(AppContext.BaseDirectory, dir, out var err)) throw err ?? new IOException("the program could not be copied");
        Ui.Log("setup.log", $"placed {dir}");
    }

    // "<Desktop>\<name>.lnk" and the Start Menu's, pointing at the app's program (replacing older ones of that name).
    static void MakeShortcuts(string exe, string dir)
    {
        var b = Brand.Current;
        var places = new[]
        {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), b.DesktopShortcut + ".lnk"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), b.StartMenuShortcut + ".lnk"),
        };
        try
        {
            dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
            foreach (var p in places)
            {
                try
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(p));
                    dynamic l = shell.CreateShortcut(p);
                    l.TargetPath = exe;
                    l.Arguments = "";
                    l.WorkingDirectory = dir;
                    l.IconLocation = exe + ",0";
                    l.WindowStyle = 1;                 // a normal window (never "Run: Minimized")
                    l.Description = b.Description;
                    l.Save();
                }
                catch (Exception ex) { Ui.Log("setup.log", $"shortcut {p}: {ex.Message}"); }
            }
        }
        catch (Exception ex) { Ui.Log("setup.log", "no shortcuts: " + ex.Message); }
    }
}
