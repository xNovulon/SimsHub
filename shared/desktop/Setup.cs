// Gets an app ready to open. The program is all anyone downloads:
//   - opened from its app folder (the usual case): the folder is brought up to date (Updater.cs);
//   - opened from anywhere else (a download): the app is installed in its usual place (Brand.InstallDir) - or that
//     copy brought up to date - with Desktop and Start Menu shortcuts, and that copy is opened instead.
using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Threading.Tasks;

namespace Novulon.Desktop;

public static class Setup
{
    // Root: the app's folder. Launch: start this program instead once this one has ended (see RunLaunch).
    // Failed: the app can't open (the user was told why).
    public record Ready(string Root, string Launch, bool Failed);

    static string _launch;
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
            return new Ready(root, up.Restart ? Environment.ProcessPath : null, false);
        }

        // opened from a download: install (or update) the app in its usual place, then open that copy
        var target = b.InstallDir;
        bool fresh = !b.IsAppFolder(target);
        Ui.Log("setup.log", $"{(fresh ? "installing" : "updating")} {b.Name} in {target} (opened from {Environment.ProcessPath})");
        status(fresh ? "Installing..." : "Getting the newest version...");
        await Task.Run(() => Updater.Run(target, status, program: false));
        if (!b.IsAppFolder(target))
        {
            Ui.Fatal("The app could not be installed",
                "Its files are downloaded from GitHub the first time, so this needs an internet connection. Check it, then open the app again.",
                Path.Combine(b.DataDir, "update", "update.log"));
            return new Ready(null, null, true);
        }
        var exe = Path.Combine(target, b.ExeName);
        try
        {
            if (await ShouldPlaceSelf(exe)) await Task.Run(() => PlaceSelf(exe));
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
    public static void SetLaunch(string exe) => _launch = exe;

    public static void RunLaunch(string[] args)
    {
        if (_launch == null) return;
        try
        {
            var psi = new ProcessStartInfo(_launch) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(_launch) };
            foreach (var a in args) psi.ArgumentList.Add(a);
            Process.Start(psi);
        }
        catch (Exception ex) { Ui.Fatal("The app was updated", "Open it again to use the new version.\n\n" + ex.Message); }
    }

    // This program goes into the app's folder when there is none there yet, or when it is the newest published build
    // and the one there is not. Otherwise the one there stays: it updates itself when it opens.
    static async Task<bool> ShouldPlaceSelf(string exe)
    {
        var self = Environment.ProcessPath;
        if (self == null || Updater.SamePath(self, exe)) return false;
        if (!File.Exists(exe)) return true;
        using var http = Ui.Web(TimeSpan.FromSeconds(30));
        var want = await Updater.PublishedSha(http);
        return want != null && Sha256(self) == want && Sha256(exe) != want;
    }

    // Copied as plain bytes, so the copy doesn't carry the download's "from the internet" mark.
    static void PlaceSelf(string exe)
    {
        var tmp = exe + ".new";
        using (var from = File.OpenRead(Environment.ProcessPath))
        using (var to = File.Create(tmp))
            from.CopyTo(to);
        File.Move(tmp, exe, true);
        Ui.Log("setup.log", $"placed {exe}");
    }

    static string Sha256(string path)
    {
        using var f = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(f)).ToLowerInvariant();
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
