// The Python an app's engine runs on - found, completed, or installed, so the app works without anyone installing
// anything first:
//   1. a Python 3.10+ that already has everything (Brand.PythonCheck) - the one that worked last time is tried first,
//      then PEP 514 registrations (python.org and Microsoft Store installs), the py launcher, and PATH;
//   2. else a Python 3.10+ gets the missing packages (pip, for this Windows user only);
//   3. else Python itself is installed first: python.org's installer, quietly and for this Windows user only (no
//      administrator needed), or Windows' own winget when python.org can't be reached.
// Everything it does is written to python-setup.log in the app's data folder.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using Microsoft.Win32;

namespace Novulon.Desktop;

public static class PythonSetup
{
    public record Python(string Exe, string[] Args, string Label);

    const string InstallerUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe";
    const string WingetId = "Python.Python.3.12";
    const string VersionCheck = "import sys; assert sys.version_info >= (3, 10)";
    static string Memo => Path.Combine(Brand.Current.DataDir, "python.txt");
    public static string LogPath => Path.Combine(Brand.Current.DataDir, "python-setup.log");
    static void Log(string line) => Ui.Log("python-setup.log", line);

    // A Python that runs the app's engine, getting it ready first when needed. null: none could be had (the caller
    // explains); a Python still missing a package is returned too - the engine's log then says what is missing.
    public static async Task<Python> Ensure(Action<string> status)
    {
        var ready = await Task.Run(Find);
        if (ready != null) return ready;
        var py = await Task.Run(Usable);
        if (py == null)
        {
            status("Installing Python (first start only, a minute or two)...");
            await Install(status);
            py = await Task.Run(Usable);
            if (py == null) { Log("no Python 3.10+ after installing"); return null; }
        }
        if (Brand.Current.PythonPackages.Length > 0)
        {
            status("Adding what the app needs to Python (first start only)...");
            await Task.Run(() => AddPackages(py));
        }
        return await Task.Run(Find) ?? py;
    }

    // A Python 3.10+ with everything the app needs, or null.
    public static Python Find()
    {
        foreach (var py in Candidates())
            if (Runs(py, VersionCheck + "; " + Brand.Current.PythonCheck))
            {
                try { File.WriteAllText(Memo, py.Exe + "\n" + string.Join(" ", py.Args)); } catch { }
                return py;
            }
        return null;
    }

    // Any Python 3.10+ (packages or not), or null.
    static Python Usable() => Candidates().FirstOrDefault(py => Runs(py, VersionCheck));

    static IEnumerable<Python> Candidates()
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        Python Add(Python p) => p != null && seen.Add(p.Exe + "|" + string.Join(" ", p.Args)) ? p : null;

        foreach (var var in new[] { "WICKED_PYTHON", "NOVULON_PYTHON" })
        {
            var env = Environment.GetEnvironmentVariable(var);
            if (!string.IsNullOrEmpty(env) && File.Exists(env)) { var p = Add(new Python(env, Array.Empty<string>(), env)); if (p != null) yield return p; }
        }
        string[] memo = null;
        try { memo = File.ReadAllLines(Memo); } catch { }
        if (memo != null && memo.Length > 0 && File.Exists(memo[0]))
        {
            var p = Add(new Python(memo[0], memo.Length > 1 && memo[1].Length > 0 ? memo[1].Split(' ') : Array.Empty<string>(), memo[0]));
            if (p != null) yield return p;
        }

        var found = new List<(Version v, string exe)>();
        foreach (var hive in new[] { RegistryHive.CurrentUser, RegistryHive.LocalMachine })
            foreach (var view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
            {
                try
                {
                    using var bk = RegistryKey.OpenBaseKey(hive, view);
                    using var core = bk.OpenSubKey(@"Software\Python\PythonCore");
                    if (core == null) continue;
                    foreach (var tag in core.GetSubKeyNames())
                    {
                        using var k = core.OpenSubKey(tag);
                        using var ip = k?.OpenSubKey("InstallPath");
                        if (ip == null) continue;
                        var exe = ip.GetValue("ExecutablePath") as string;
                        if (string.IsNullOrEmpty(exe)) exe = Path.Combine(ip.GetValue("") as string ?? "", "python.exe");
                        var ver = (k.GetValue("SysVersion") as string) ?? tag;
                        var m = Regex.Match(ver, @"^(\d+)\.(\d+)");
                        if (!m.Success || !File.Exists(exe)) continue;
                        var v = new Version(int.Parse(m.Groups[1].Value), int.Parse(m.Groups[2].Value));
                        if (v.Major == 3 && v.Minor >= 10) found.Add((v, exe));
                    }
                }
                catch { /* unreadable key */ }
            }
        foreach (var f in found.OrderByDescending(f => f.v))
        {
            var p = Add(new Python(f.exe, Array.Empty<string>(), $"Python {f.v}"));
            if (p != null) yield return p;
        }
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        foreach (var py in new[] {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "py.exe"),
            Path.Combine(local, "Programs", "Python", "Launcher", "py.exe") })
            if (File.Exists(py)) { var p = Add(new Python(py, new[] { "-3" }, "py -3")); if (p != null) yield return p; }
        // where python.org's installer puts a per-user Python (found even before Windows re-reads PATH)
        var programs = Path.Combine(local, "Programs", "Python");
        if (Directory.Exists(programs))
            foreach (var dir in Directory.EnumerateDirectories(programs, "Python3*").OrderByDescending(d => d, StringComparer.OrdinalIgnoreCase))
            {
                var exe = Path.Combine(dir, "python.exe");
                if (File.Exists(exe)) { var p = Add(new Python(exe, Array.Empty<string>(), exe)); if (p != null) yield return p; }
            }
        var apps = Path.Combine(local, "Microsoft", "WindowsApps");
        foreach (var dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
        {
            string exe;
            try
            {
                exe = Path.Combine(dir.Trim(), "python.exe");
                if (!File.Exists(exe)) continue;
                // the Microsoft Store "python.exe" is only a real Python when a Python package is installed
                if (string.Equals(Path.GetFullPath(dir.Trim()).TrimEnd('\\'), apps, StringComparison.OrdinalIgnoreCase)
                    && !Directory.EnumerateDirectories(apps, "PythonSoftwareFoundation.Python.3*").Any()) continue;
            }
            catch { continue; }   // bad PATH entry
            var p = Add(new Python(exe, Array.Empty<string>(), exe));
            if (p != null) yield return p;
        }
    }

    // Does this code run on that Python? (hidden, at most 20 s)
    static bool Runs(Python py, string code)
    {
        try { return Ui.RunHidden(py.Exe, py.Args.Concat(new[] { "-c", code }).ToArray(), TimeSpan.FromSeconds(20)).Code == 0; }
        catch { return false; }
    }

    static void AddPackages(Python py)
    {
        var pip = py.Args.Concat(new[] { "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location", "--user" })
                    .Concat(Brand.Current.PythonPackages).ToArray();
        try
        {
            var r = Ui.RunHidden(py.Exe, pip, TimeSpan.FromMinutes(15));
            Log($"pip ({py.Label}) exit {r.Code}:\n{r.Output}");
            if (r.Code != 0 && r.Output.Contains("--user"))
            {
                // a virtual environment has no per-user packages: install into it instead
                r = Ui.RunHidden(py.Exe, pip.Where(a => a != "--user").ToArray(), TimeSpan.FromMinutes(15));
                Log($"pip without --user exit {r.Code}:\n{r.Output}");
            }
        }
        catch (Exception ex) { Log("pip could not run: " + ex.Message); }
    }

    static async Task Install(Action<string> status)
    {
        var setup = Path.Combine(Path.GetTempPath(), Path.GetFileName(InstallerUrl));
        try
        {
            using var http = Ui.Web(TimeSpan.FromMinutes(15));
            await Ui.Download(http, InstallerUrl, setup, p => status($"Downloading Python ({p:P0})..."));
            status("Installing Python (first start only, a minute or two)...");
            var r = await Task.Run(() => Ui.RunHidden(setup, new[] {
                "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1", "InstallLauncherAllUsers=0",
                "Include_test=0", "Include_doc=0", "Shortcuts=0", "AssociateFiles=0" }, TimeSpan.FromMinutes(15)));
            Log($"python.org installer exit {r.Code}");
            if (r.Code == 0) return;
        }
        catch (Exception ex) { Log("python.org installer: " + ex.Message); }
        finally { try { File.Delete(setup); } catch { } }

        // python.org unreachable or its installer failed: Windows' own package manager
        var winget = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Microsoft", "WindowsApps", "winget.exe");
        if (!File.Exists(winget)) { Log("winget is not on this PC"); return; }
        status("Installing Python with Windows' installer (first start only)...");
        try
        {
            var r = await Task.Run(() => Ui.RunHidden(winget, new[] {
                "install", "--id", WingetId, "--exact", "--scope", "user", "--silent",
                "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity" }, TimeSpan.FromMinutes(15)));
            Log($"winget exit {r.Code}:\n{r.Output}");
        }
        catch (Exception ex) { Log("winget: " + ex.Message); }
    }
}
