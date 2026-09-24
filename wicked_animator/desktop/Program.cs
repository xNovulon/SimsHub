// Novulon's Wicked Animator - the desktop app.
//
// A real Windows window (Microsoft Edge WebView2, part of Windows 11) around the animator, and its engine - the local
// server in backend\server.py - started quietly in the background: no console window, no browser. Closing the window
// first has the page write any unfinished work to the recovery file, then stops the engine (only if this window
// started it). Opening the app again while it is open brings the open window to the front; opening it while it is
// still closing waits for that and then opens it fresh. Every start first brings the animator up to date from GitHub
// (Updater.cs).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using Microsoft.Win32;

namespace WickedAnimator;

static class App
{
    public const string Name = "Novulon's Wicked Animator";
    public const string Version = "1.0.0";
    public const int Port = 8765;
    public static readonly string Url = $"http://127.0.0.1:{Port}/";
    public static readonly string DataDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NovulonWickedAnimator");
    public static int ShowMessage;          // a second copy asks the open window to come to the front
    public static bool RestartAfterExit;    // the update replaced this program: open the new one once this one ends
    public static string Commit;            // the GitHub version this folder has (short), when known
    const string MutexName = @"Local\Novulon.WickedAnimator";
    const string ClosingName = @"Local\Novulon.WickedAnimator.Closing";
    static EventWaitHandle _closing;

    // the page's colours (web/css/app.css)
    public static readonly Color Bg = Color.FromArgb(0x0b, 0x0a, 0x10);
    public static readonly Color Pink = Color.FromArgb(0xff, 0x4f, 0x9a);
    public static readonly Color Purple = Color.FromArgb(0x8b, 0x5c, 0xf6);
    public static readonly Color Muted = Color.FromArgb(0xa7, 0x9f, 0xb8);

    [STAThread]
    static void Main(string[] args)
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        Application.EnableVisualStyles();                 // before any dialog (TaskDialog needs them)
        Application.SetCompatibleTextRenderingDefault(false);
        ShowMessage = Native.RegisterWindowMessage("Novulon.WickedAnimator.Show");

        var single = new Mutex(true, MutexName, out bool owned);
        if (!owned)
        {
            bool closing = EventWaitHandle.TryOpenExisting(ClosingName, out var mark) && mark.WaitOne(0);
            mark?.Dispose();
            if (!closing)
            {
                // already open: bring that window to the front (and let it take the foreground)
                Native.AllowSetForegroundWindow(-1);
                Native.PostMessage((IntPtr)0xffff, ShowMessage, IntPtr.Zero, IntPtr.Zero);   // HWND_BROADCAST
                return;
            }
            // the open copy is saving and shutting down: wait for it, then open afresh
            try { owned = single.WaitOne(TimeSpan.FromSeconds(20)); }
            catch (AbandonedMutexException) { owned = true; }
            if (!owned)
            {
                Fatal("The animator is still closing", "Wait a moment, then open it again.");
                return;
            }
        }
        try
        {
            _closing = new EventWaitHandle(false, EventResetMode.ManualReset, ClosingName);
            _closing.Reset();
            Directory.CreateDirectory(DataDir);
            Application.ThreadException += (_, e) => Fatal("Something went wrong", e.Exception.Message);
            Application.Run(new Launcher(args));
        }
        finally
        {
            try { single.ReleaseMutex(); } catch { }
            single.Dispose();
        }
        if (RestartAfterExit)
        {
            try
            {
                var psi = new ProcessStartInfo(Environment.ProcessPath) { UseShellExecute = false, WorkingDirectory = Root };
                foreach (var a in args) psi.ArgumentList.Add(a);
                Process.Start(psi);
            }
            catch (Exception ex) { Fatal("The animator was updated", "Open it again to use the new version.\n\n" + ex.Message); }
        }
    }

    // the window is hidden and saving: a copy opened now waits for it instead of doing nothing
    public static void MarkClosing() { try { _closing?.Set(); } catch { } }

    // The animator folder (web\ and backend\): next to this program, or a folder above it.
    static string _root;
    public static string Root
    {
        get
        {
            if (_root != null) return _root;
            var starts = new[] { AppContext.BaseDirectory, Path.GetDirectoryName(Environment.ProcessPath ?? "") ?? "" };
            foreach (var start in starts)
            {
                var d = new DirectoryInfo(start);
                for (int i = 0; d != null && i < 4; i++, d = d.Parent)
                    if (File.Exists(Path.Combine(d.FullName, "backend", "server.py")) && Directory.Exists(Path.Combine(d.FullName, "web")))
                        return _root = d.FullName;
            }
            return _root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Tools", "sims4_animator");
        }
    }

    public static Stream Resource(string name) => Assembly.GetExecutingAssembly().GetManifestResourceStream(name);

    public static Icon LoadIcon()
    {
        try { using var s = Resource("logo.ico"); return new Icon(s); } catch { return null; }
    }

    public static void OpenExternal(string uri)
    {
        try { Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true }); } catch { /* nothing to open it with */ }
    }

    public static void Fatal(string heading, string text, string logPath = null)
    {
        var page = new TaskDialogPage
        {
            Caption = Name, Heading = heading, Text = text, Icon = TaskDialogIcon.Error,
            Buttons = { TaskDialogButton.Close },
        };
        if (logPath != null && File.Exists(logPath))
        {
            var open = new TaskDialogButton("Open the log");
            open.Click += (_, _) => OpenExternal(logPath);
            open.AllowCloseDialog = false;
            page.Buttons.Insert(0, open);
        }
        TaskDialog.ShowDialog(page);
    }
}

// Shows the splash card, then the main window once the page has loaded.
sealed class Launcher : ApplicationContext
{
    public Launcher(string[] args)
    {
        var splash = new Splash();
        var main = new MainForm(args, splash);
        main.FormClosed += (_, _) => ExitThread();
        // closing the splash card while starting (Alt+F4) ends the app
        splash.FormClosed += (_, _) => { if (main.Starting && !main.IsDisposed) main.Abandon(); };
        splash.Show();
        main.Begin();
    }
}

// ---------------------------------------------------------------------------------------------------- the engine
// The Python server in backend\server.py, run without a console window. Its output goes to engine.log.
sealed class Engine
{
    // loopback never goes through a proxy (a system proxy could otherwise swallow the check)
    static readonly HttpClient Http = new(new SocketsHttpHandler { UseProxy = false, ConnectTimeout = TimeSpan.FromSeconds(1) })
    {
        Timeout = TimeSpan.FromSeconds(3),
    };
    public static readonly string LogPath = Path.Combine(App.DataDir, "engine.log");
    static readonly string PythonMemo = Path.Combine(App.DataDir, "python.txt");

    Process _proc;
    IntPtr _job;
    StreamWriter _log;
    readonly object _logLock = new();
    public bool Stopping;
    public DateTime Started;
    public event Action<int> Exited;           // exit code (the engine stopped by itself)

    public bool Owned => _proc != null;
    public bool Running { get { try { return _proc != null && !_proc.HasExited; } catch { return false; } } }

    // Kind "ok": our engine answers (any reply that names itself WickedAnimator, errors included);
    // "other": something else holds the port. null: nothing is listening yet.
    public record Status(string Kind, long Build, int Pid);

    static bool PortListening()
    {
        try
        {
            return IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners()
                .Any(e => e.Port == App.Port && e.AddressFamily == AddressFamily.InterNetwork);
        }
        catch { return true; }   // cannot tell: ask over HTTP
    }

    public static async Task<Status> StatusAsync()
    {
        if (!PortListening()) return null;
        try
        {
            using var r = await Http.GetAsync(App.Url + "api/status");
            var body = await r.Content.ReadAsStringAsync();
            bool ours = r.Headers.Server.Any(p => string.Equals(p.Product?.Name, "WickedAnimator", StringComparison.OrdinalIgnoreCase));
            if (!ours && !(r.IsSuccessStatusCode && body.Contains("\"ok\""))) return new Status("other", 0, 0);
            long build = 0; int pid = 0;
            try
            {
                using var j = JsonDocument.Parse(body);
                if (j.RootElement.TryGetProperty("build", out var b)) build = b.ValueKind == JsonValueKind.Number ? b.GetInt64() : long.Parse(b.GetString() ?? "0");
                if (j.RootElement.TryGetProperty("pid", out var p) && p.ValueKind == JsonValueKind.Number) pid = p.GetInt32();
            }
            catch { /* an older engine, or an error reply */ }
            return new Status("ok", build, pid);
        }
        catch (HttpRequestException) { return null; }
        catch (TaskCanceledException) { return null; }
    }

    // The newest change to the engine's code (Unix seconds, like server.py's BUILD).
    public static long CurrentBuild()
    {
        try
        {
            return Directory.EnumerateFiles(Path.Combine(App.Root, "backend"), "*.py")
                .Select(f => new DateTimeOffset(File.GetLastWriteTimeUtc(f)).ToUnixTimeSeconds()).DefaultIfEmpty(0).Max();
        }
        catch { return 0; }
    }

    // An engine left running from before (older code, not started by this window): stop it so a fresh one can
    // start. Only a Python process is ever stopped.
    public static async Task<bool> StopStale(int pid)
    {
        if (pid <= 0) pid = Native.ListenerPid(App.Port);
        if (pid <= 0) return false;
        try
        {
            using var p = Process.GetProcessById(pid);
            if (!p.ProcessName.StartsWith("python", StringComparison.OrdinalIgnoreCase)) return false;
            p.Kill(true);
            p.WaitForExit(3000);
        }
        catch { return false; }
        for (int i = 0; i < 50; i++)
        {
            if (!PortListening()) return true;
            await Task.Delay(100);
        }
        return !PortListening();
    }

    public record Python(string Exe, string[] Args, string Label);

    // Python 3.10+ that can load the engine's parts (numpy, Pillow, protobuf). The one that worked last time comes
    // first; then PEP 514 registrations (python.org and Microsoft Store installs), the py launcher, and PATH.
    public static Python FindPython()
    {
        var list = Candidates().ToList();
        foreach (var py in list)
            if (HasParts(py)) { try { File.WriteAllText(PythonMemo, py.Exe + "\n" + string.Join(" ", py.Args)); } catch { } return py; }
        return list.FirstOrDefault();      // none has every part: start anyway - the log then says what is missing
    }

    static IEnumerable<Python> Candidates()
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        Python Add(Python p) => p != null && seen.Add(p.Exe + "|" + string.Join(" ", p.Args)) ? p : null;

        var env = Environment.GetEnvironmentVariable("WICKED_PYTHON");
        if (!string.IsNullOrEmpty(env) && File.Exists(env)) { var p = Add(new Python(env, Array.Empty<string>(), env)); if (p != null) yield return p; }
        string[] memo = null;
        try { memo = File.ReadAllLines(PythonMemo); } catch { }
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
                        var m = System.Text.RegularExpressions.Regex.Match(ver, @"^(\d+)\.(\d+)");
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
        foreach (var py in new[] {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "py.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Launcher", "py.exe") })
            if (File.Exists(py)) { var p = Add(new Python(py, new[] { "-3" }, "py -3")); if (p != null) yield return p; }
        var apps = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Microsoft", "WindowsApps");
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

    // Can this Python load the engine's parts? (hidden, at most 20 s)
    static bool HasParts(Python py)
    {
        try
        {
            var psi = new ProcessStartInfo(py.Exe)
            {
                UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true,
            };
            foreach (var a in py.Args) psi.ArgumentList.Add(a);
            psi.ArgumentList.Add("-c");
            psi.ArgumentList.Add("import sys; assert sys.version_info >= (3, 10); import numpy, PIL, google.protobuf");
            using var p = Process.Start(psi);
            _ = p.StandardOutput.ReadToEndAsync();
            _ = p.StandardError.ReadToEndAsync();
            if (!p.WaitForExit(20000)) { try { p.Kill(true); } catch { } return false; }
            return p.ExitCode == 0;
        }
        catch { return false; }
    }

    public void Start(Python py)
    {
        Stopping = false;
        OpenLog();
        var psi = new ProcessStartInfo(py.Exe)
        {
            WorkingDirectory = App.Root,
            UseShellExecute = false,
            CreateNoWindow = true,                      // no console window, ever
            WindowStyle = ProcessWindowStyle.Hidden,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        foreach (var a in py.Args) psi.ArgumentList.Add(a);
        psi.ArgumentList.Add("-u");
        psi.ArgumentList.Add(Path.Combine(App.Root, "backend", "server.py"));
        psi.Environment["PYTHONIOENCODING"] = "utf-8";    // names in any language print fine into the log
        psi.Environment["PYTHONUTF8"] = "1";
        psi.Environment.Remove("ANIMATOR_PORT");          // always the usual port (and the usual recovery file)
        Log($"--- {DateTime.Now:yyyy-MM-dd HH:mm:ss} starting the engine with {py.Label}: {py.Exe}");
        var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        proc.OutputDataReceived += (_, e) => { if (e.Data != null) Log(e.Data); };
        proc.ErrorDataReceived += (_, e) => { if (e.Data != null) Log(e.Data); };
        proc.Exited += (_, _) =>
        {
            int code = -1;
            try { code = proc.ExitCode; } catch { }
            Log($"--- the engine stopped (exit code {code})");
            if (!Stopping && ReferenceEquals(proc, _proc)) Exited?.Invoke(code);
        };
        _proc = proc;
        proc.Start();
        Started = DateTime.Now;
        TieToThisWindow(proc);
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();
    }

    // The engine lives only as long as this program: if the app is closed (or crashes) Windows ends it too.
    void TieToThisWindow(Process p)
    {
        try
        {
            if (_job == IntPtr.Zero)
            {
                _job = Native.CreateJobObject(IntPtr.Zero, null);
                var info = new Native.JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
                // kill on close; programs the engine opens (Explorer "show in folder") are not part of it
                info.BasicLimitInformation.LimitFlags = 0x2000 | 0x1000;
                int size = Marshal.SizeOf(info);
                IntPtr ptr = Marshal.AllocHGlobal(size);
                try
                {
                    Marshal.StructureToPtr(info, ptr, false);
                    Native.SetInformationJobObject(_job, 9, ptr, (uint)size);
                }
                finally { Marshal.FreeHGlobal(ptr); }
            }
            Native.AssignProcessToJobObject(_job, p.Handle);
        }
        catch (Exception ex) { Log("(could not tie the engine to the window: " + ex.Message + ")"); }
    }

    public void Stop()
    {
        Stopping = true;
        try { if (_proc != null && !_proc.HasExited) { _proc.Kill(true); _proc.WaitForExit(3000); } } catch { }
        lock (_logLock) { try { _log?.Dispose(); } catch { } _log = null; }
    }

    void OpenLog()
    {
        lock (_logLock)
        {
            if (_log != null) return;
            try
            {
                var fi = new FileInfo(LogPath);
                bool big = fi.Exists && fi.Length > 2_000_000;
                if (big) File.Copy(LogPath, Path.Combine(App.DataDir, "engine.old.log"), true);
                _log = new StreamWriter(new FileStream(LogPath, big ? FileMode.Create : FileMode.Append, FileAccess.Write, FileShare.ReadWrite),
                    new UTF8Encoding(false)) { AutoFlush = true };
            }
            catch { _log = null; }
        }
    }

    public void Log(string line)
    {
        lock (_logLock) { try { _log?.WriteLine(line); } catch { } }
    }

    public static string LogTail(int lines = 12)
    {
        try
        {
            using var fs = new FileStream(LogPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
            using var sr = new StreamReader(fs);
            var all = sr.ReadToEnd().Split('\n').Select(l => l.TrimEnd('\r')).Where(l => l.Length > 0).ToArray();
            return string.Join("\n", all.Skip(Math.Max(0, all.Length - lines)));
        }
        catch { return ""; }
    }
}

// ---------------------------------------------------------------------------------------------------- main window
sealed class MainForm : Form
{
    readonly WebView2 _web = new() { Dock = DockStyle.Fill };
    readonly Engine _engine = new();
    readonly Splash _splash;
    readonly bool _devtools;
    CoreWebView2Environment _env;
    Engine.Python _python;
    bool _closeReady, _closing, _shown, _waiting;
    public bool Starting = true;
    int _restarts, _navFailures;
    DateTime _firstRestart;
    DateTime _hungSince = DateTime.MinValue;
    bool _hungAsking;
    // full screen (F11, or when the page asks for it)
    bool _full;
    FormWindowState _fullWasState;
    Rectangle _fullWasBounds;

    public MainForm(string[] args, Splash splash)
    {
        _splash = splash;
        _devtools = args.Contains("--devtools");
        Text = App.Name;
        Icon = App.LoadIcon();
        BackColor = App.Bg;
        MinimumSize = new Size(1000, 620);
        StartPosition = FormStartPosition.Manual;
        KeyPreview = true;
        _web.DefaultBackgroundColor = App.Bg;
        Controls.Add(_web);
        Placement.Restore(this);
        _web.KeyDown += (_, e) => { if (HandleKey(e.KeyData)) e.Handled = true; };
        _engine.Exited += code => { try { if (!IsDisposed) BeginInvoke(new Action(() => EngineStopped(code))); } catch { } };
        CreateHandle();                               // hidden until the page has loaded
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        Native.StyleTitleBar(Handle, Color.FromArgb(0x15, 0x12, 0x1d));
    }

    protected override void WndProc(ref Message m)
    {
        if (App.ShowMessage != 0 && m.Msg == App.ShowMessage)
        {
            if (Visible) Native.BringToFront(Handle);
            else if (!_splash.IsDisposed && _splash.Visible) Native.BringToFront(_splash.Handle);
            return;
        }
        base.WndProc(ref m);
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        if (HandleKey(keyData)) return true;
        return base.ProcessCmdKey(ref msg, keyData);
    }

    bool HandleKey(Keys k)
    {
        if (k == Keys.F11) { SetFull(!_full); return true; }
        if (k == Keys.F12 && _devtools) { _web.CoreWebView2?.OpenDevToolsWindow(); return true; }
        return false;
    }

    void HideSplash() { if (!_splash.IsDisposed) _splash.Hide(); }

    // The user closed the splash card while starting: end quietly (no error about the start being cut short).
    bool _abandoned;
    public void Abandon()
    {
        _abandoned = true;
        Quit();
    }

    // Startup failed or was given up: end the app cleanly (never leave an invisible process behind).
    void Quit()
    {
        Starting = false;
        HideSplash();
        if (!IsDisposed) Close();
    }

    // -------------------------------------------------------------- start up
    public async void Begin()
    {
        try
        {
            // 0. the newest version from GitHub (Updater.cs: quick when there is nothing new, skipped offline)
            Action<string> say = s => { try { _splash.BeginInvoke(new Action(() => _splash.SetStatus(s))); } catch { } };
            var update = await Task.Run(() => Updater.Run(say));
            if (_abandoned || IsDisposed) return;
            if (update.Restart)
            {
                App.RestartAfterExit = true;             // Main opens the new program once this one has ended
                Quit(); return;
            }
            App.Commit = Updater.InstalledCommit();

            // 1. the engine: reuse one that already runs (e.g. started by the Sims Hub) unless its code is older
            var status = await Engine.StatusAsync();
            if (status?.Kind == "other")
            {
                HideSplash();
                App.Fatal("Another program is using the animator's port",
                    $"Something else on this PC answers at {App.Url}. Close it (or restart the PC) and open the animator again.");
                Quit(); return;
            }
            if (status?.Kind == "ok" && status.Build < Engine.CurrentBuild())
            {
                _splash.SetStatus("Updating the studio...");
                if (await Engine.StopStale(status.Pid)) status = null;
            }
            if (status == null)
            {
                _splash.SetStatus("Starting the studio...");
                _python = await Task.Run(Engine.FindPython);
                if (_python == null) { NoPython(); return; }
                _engine.Start(_python);
                _waiting = true;
                try { if (!await WaitForEngine()) return; } finally { _waiting = false; }
            }

            // 2. the window's web view
            _splash.SetStatus("Opening the stage...");
            var env = _env = await CreateEnvironment();
            if (env == null) return;
            _ = _web.Handle;                // the view needs its handle (the window stays hidden until loaded)
            await _web.EnsureCoreWebView2Async(env);
            Configure(_web.CoreWebView2);
            _web.CoreWebView2.Navigate(App.Url);
        }
        catch (Exception ex)
        {
            if (_abandoned || _closing || IsDisposed) return;
            HideSplash();
            App.Fatal("The animator could not start", ex.Message, Engine.LogPath);
            Quit();
        }
    }

    async Task<bool> WaitForEngine()
    {
        var t0 = DateTime.Now;
        while (true)
        {
            await Task.Delay(100);
            if ((await Engine.StatusAsync())?.Kind == "ok") return true;
            var secs = (DateTime.Now - t0).TotalSeconds;
            if (_abandoned || IsDisposed) return false;
            if (!_engine.Running)
            {
                EngineFailed("The animator's engine stopped while starting.");
                return false;
            }
            if (secs > 6) _splash.SetStatus("Getting your mods ready - the first start can take a minute...");
            if (secs > 180)
            {
                EngineFailed("The animator's engine did not answer in time.");
                return false;
            }
        }
    }

    async Task<CoreWebView2Environment> CreateEnvironment()
    {
        try
        {
            // WebView2Loader.dll travels inside this program; it is written next to the window's data once
            var dir = Path.Combine(App.DataDir, "runtime", "1.0.3179.45");
            var dll = Path.Combine(dir, "WebView2Loader.dll");
            using (var s = App.Resource("WebView2Loader.dll"))
            {
                if (!File.Exists(dll) || new FileInfo(dll).Length != s.Length)
                {
                    Directory.CreateDirectory(dir);
                    var tmp = dll + ".tmp";
                    using (var f = File.Create(tmp)) s.CopyTo(f);
                    File.Move(tmp, dll, true);
                }
            }
            CoreWebView2Environment.SetLoaderDllFolderPath(dir);
            // sounds may play without a click first - this is an app, not a web page. On PCs with two graphics
            // chips (a laptop's built-in one and a gaming one) the 3D view and motion capture use the faster one.
            var args = "--autoplay-policy=no-user-gesture-required --force_high_performance_gpu";
            // automated tests can drive the window (WICKED_DEBUG_PORT=9229)
            var debugPort = Environment.GetEnvironmentVariable("WICKED_DEBUG_PORT");
            if (int.TryParse(debugPort, out int dp) && dp > 1024) args += $" --remote-debugging-port={dp}";
            var opts = new CoreWebView2EnvironmentOptions(args);
            return await CoreWebView2Environment.CreateAsync(null, Path.Combine(App.DataDir, "WebView2"), opts);
        }
        catch (WebView2RuntimeNotFoundException)
        {
            HideSplash();
            var page = new TaskDialogPage
            {
                Caption = App.Name, Icon = TaskDialogIcon.Warning,
                Heading = "Microsoft Edge WebView2 is needed",
                Text = "The animator's window needs Microsoft Edge WebView2 (free, from Microsoft). Click \"Get WebView2\", "
                     + "open the file it downloads (MicrosoftEdgeWebview2Setup.exe) to install it, then open the animator again.",
            };
            var get = new TaskDialogButton("Get WebView2");
            page.Buttons.Add(get);
            page.Buttons.Add(TaskDialogButton.Close);
            if (TaskDialog.ShowDialog(page) == get)
                App.OpenExternal("https://go.microsoft.com/fwlink/p/?LinkId=2124703");   // Microsoft's Evergreen installer
            Quit();
            return null;
        }
    }

    void Configure(CoreWebView2 w)
    {
        var s = w.Settings;
        s.AreDefaultContextMenusEnabled = false;     // right-drag looks around; the app has its own menus
        s.AreDevToolsEnabled = _devtools;
        s.IsStatusBarEnabled = false;
        s.IsZoomControlEnabled = false;              // Ctrl+wheel must not zoom the whole app
        s.AreBrowserAcceleratorKeysEnabled = false;  // no print/find/reload - the app's own shortcuts still work
        s.IsPasswordAutosaveEnabled = false;
        s.IsGeneralAutofillEnabled = false;
        s.IsSwipeNavigationEnabled = false;
        s.IsPinchZoomEnabled = false;
        s.IsBuiltInErrorPageEnabled = false;
        _web.AllowExternalDrop = false;              // a file or link dropped on the window does nothing
        _ = w.AddScriptToExecuteOnDocumentCreatedAsync($"window.wickedDesktop = {{ version: '{App.Version}', commit: '{App.Commit ?? ""}' }};");

        w.NavigationStarting += (_, e) =>
        {
            if (IsOwn(e.Uri) || e.Uri == "about:blank") return;
            e.Cancel = true;                          // links to the web open in the normal browser
            if (e.Uri.StartsWith("http", StringComparison.OrdinalIgnoreCase) || e.Uri.StartsWith("mailto:", StringComparison.OrdinalIgnoreCase))
                App.OpenExternal(e.Uri);
        };
        w.NewWindowRequested += (_, e) =>
        {
            e.Handled = true;
            if (e.Uri.StartsWith("http", StringComparison.OrdinalIgnoreCase) && !IsOwn(e.Uri)) App.OpenExternal(e.Uri);
        };
        w.PermissionRequested += (_, e) =>
        {
            // the app's own page may use the camera/microphone (capture), clipboard and so on
            e.State = IsOwn(e.Uri) ? CoreWebView2PermissionState.Allow : CoreWebView2PermissionState.Deny;
        };
        w.DocumentTitleChanged += (_, _) =>
        {
            var t = w.DocumentTitle;
            Text = string.IsNullOrWhiteSpace(t) || t.StartsWith("127.0.0.1") ? App.Name : t;
        };
        w.ContainsFullScreenElementChanged += (_, _) => SetFull(w.ContainsFullScreenElement);
        // some pages (about:srcdoc...) open without NavigationStarting: whatever leaves the app comes back to it
        // (the page wrote any unfinished work to the recovery file on the way out, so it is offered again)
        w.SourceChanged += (_, _) =>
        {
            if (_closing || !_shown || IsOwn(w.Source)) return;
            _engine.Log($"(left the app for {w.Source} - going back)");
            w.Navigate(App.Url);
        };
        w.NavigationCompleted += async (_, e) =>
        {
            if (_closing) return;
            if (!e.IsSuccess)
            {
                // cancelled (a link that opened outside) or replaced by a newer navigation: the page is still there
                if (e.WebErrorStatus == CoreWebView2WebErrorStatus.OperationCanceled) return;
                _navFailures++;
                bool young = _engine.Running && (DateTime.Now - _engine.Started).TotalSeconds < 180;
                if (!_shown && (e.HttpStatusCode >= 400 || (_navFailures > 60 && !young)))
                {
                    EngineFailed(e.HttpStatusCode >= 400 ? $"The animator's page could not be opened (error {e.HttpStatusCode})."
                                                         : "The animator's engine stopped answering while starting.");
                    return;
                }
                // the engine may be restarting: try again shortly
                await Task.Delay(800);
                if (!_closing) w.Navigate(App.Url);
                return;
            }
            _navFailures = 0;
            if (!_shown && IsOwn(w.Source)) Reveal();
        };
        w.ProcessFailed += async (_, e) =>
        {
            if (_closing) return;
            _engine.Log($"(window process failed: {e.ProcessFailedKind})");
            if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited)
            {
                App.Fatal("The window stopped unexpectedly",
                    "Open the animator again - your unfinished work is offered back when it opens.");
                _closeReady = true;
                Close();
                return;
            }
            if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessExited)
            {
                await Task.Delay(300);
                try { w.Reload(); } catch { }
                return;
            }
            // busy is not dead: long work (physics, a big export) must never be thrown away by a reload
            if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessUnresponsive && _hungSince == DateTime.MinValue)
            {
                _hungSince = DateTime.Now;
                _ = WatchHung(w);
            }
        };
    }

    // The page stopped answering: wait for it; only after a full minute offer to reload it.
    async Task WatchHung(CoreWebView2 w)
    {
        try
        {
            var alive = w.ExecuteScriptAsync("1");   // completes as soon as the page's main thread is free again
            while (!_closing)
            {
                if (await Task.WhenAny(alive, Task.Delay(1000)) == alive) return;
                if (_hungAsking || (DateTime.Now - _hungSince).TotalSeconds < 60) continue;
                _hungAsking = true;
                var page = new TaskDialogPage
                {
                    Caption = App.Name, Icon = TaskDialogIcon.Warning,
                    Heading = "The animator is busy",
                    Text = "It has been working on something for over a minute. Wait for it, or reload - your work from a few seconds ago is offered back after reloading.",
                };
                var wait = new TaskDialogButton("Wait");
                var reload = new TaskDialogButton("Reload");
                page.Buttons.Add(wait);
                page.Buttons.Add(reload);
                var pick = TaskDialog.ShowDialog(this, page);
                _hungAsking = false;
                if (pick == reload)
                {
                    // a stuck script can't be stopped by Reload(): end the page's process; RenderProcessExited reloads it
                    try
                    {
                        foreach (var pi in _env.GetProcessInfos())
                            if (pi.Kind == CoreWebView2ProcessKind.Renderer)
                                try { using var rp = Process.GetProcessById(pi.ProcessId); rp.Kill(); } catch { }
                    }
                    catch { try { w.Reload(); } catch { } }
                    return;
                }
                _hungSince = DateTime.Now;           // wait another minute before asking again
            }
        }
        catch { }
        finally { _hungSince = DateTime.MinValue; }
    }

    static bool IsOwn(string uri) =>
        uri != null && (uri.StartsWith(App.Url, StringComparison.OrdinalIgnoreCase)
                        || uri.StartsWith($"http://localhost:{App.Port}/", StringComparison.OrdinalIgnoreCase));

    void Reveal()
    {
        _shown = true;
        Starting = false;
        _splash.TopMost = true;
        var want = WindowState;                       // Normal or Maximized, from Placement.Restore
        Show();
        // a shortcut set to "Run: Minimized" turns the first Show into a minimize: undo it
        if (WindowState == FormWindowState.Minimized && want != FormWindowState.Minimized) WindowState = want;
        Native.BringToFront(Handle);
        _web.Focus();
        _splash.FadeOut();
    }

    // -------------------------------------------------------------- the engine stopping / not found
    async void EngineStopped(int code)
    {
        if (_closing || _waiting) return;             // WaitForEngine reports a stop while starting
        // stopped while in use: start it again (the page keeps everything; it only waits a moment)
        if ((DateTime.Now - _firstRestart).TotalMinutes > 2) { _firstRestart = DateTime.Now; _restarts = 0; }
        if (_python == null) _python = await Task.Run(Engine.FindPython);   // the engine was one this window reused
        if (_closing) return;
        if (_python != null && _restarts++ < 3)
        {
            try { _engine.Start(_python); return; } catch (Exception ex) { _engine.Log("restart failed: " + ex.Message); }
        }
        if (!_shown) { EngineFailed("The animator's engine stopped while starting."); return; }
        App.Fatal("The animator's engine keeps stopping",
            "Your unfinished work is kept. Close the animator and open it again.\n\nLast messages:\n" + Engine.LogTail(8), Engine.LogPath);
    }

    void EngineFailed(string what)
    {
        _engine.Stop();
        var tail = Engine.LogTail();
        var hint = tail.Contains("No module named") ? "\n\nA Python part is missing - see the log."
                 : tail.Contains("in use") ? $"\n\nPort {App.Port} is in use by another program."
                 : "";
        HideSplash();
        App.Fatal(what, "Last messages from the engine:\n" + (tail.Length > 0 ? tail : "(none)") + hint, Engine.LogPath);
        Quit();
    }

    void NoPython()
    {
        HideSplash();
        var page = new TaskDialogPage
        {
            Caption = App.Name, Icon = TaskDialogIcon.Warning,
            Heading = "Python is needed",
            Text = "The animator's engine runs on Python 3 (free). Install Python 3.12 or newer from python.org - tick \"Add python.exe to PATH\" - then open the animator again.",
        };
        var get = new TaskDialogButton("Get Python");
        page.Buttons.Add(get);
        page.Buttons.Add(TaskDialogButton.Close);
        if (TaskDialog.ShowDialog(page) == get) App.OpenExternal("https://www.python.org/downloads/windows/");
        Quit();
    }

    // -------------------------------------------------------------- full screen
    void SetFull(bool on)
    {
        if (on == _full) return;
        _full = on;
        if (on)
        {
            _fullWasState = WindowState;
            _fullWasBounds = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            FormBorderStyle = FormBorderStyle.None;
            WindowState = FormWindowState.Normal;
            Bounds = Screen.FromControl(this).Bounds;
        }
        else
        {
            FormBorderStyle = FormBorderStyle.Sizable;
            Bounds = _fullWasBounds;
            WindowState = _fullWasState;
        }
    }

    // -------------------------------------------------------------- closing
    protected override async void OnFormClosing(FormClosingEventArgs e)
    {
        if (_closeReady || _web.CoreWebView2 == null || !_shown || e.CloseReason == CloseReason.WindowsShutDown)
        {
            if (_shown && !_full) Placement.Save(this);
            base.OnFormClosing(e);
            return;
        }
        e.Cancel = true;
        if (_closing) return;
        _closing = true;
        App.MarkClosing();
        if (_full) SetFull(false);
        Placement.Save(this);
        Hide();                                       // feels instant
        try
        {
            // 1. the page saves unfinished work to the recovery file and says when it is written (no size limit)
            var flush = _web.CoreWebView2.ExecuteScriptAsync("window.wickedFlushSync ? String(window.wickedFlushSync()) : 'none'");
            await Task.WhenAny(flush, Task.Delay(5000));
            // 2. leaving the page runs its "pagehide" step too (a second chance, e.g. an older page)
            var left = new TaskCompletionSource<bool>();
            void Done(object s, CoreWebView2NavigationCompletedEventArgs a) => left.TrySetResult(true);
            _web.CoreWebView2.NavigationCompleted += Done;
            _web.CoreWebView2.Navigate("about:blank");
            await Task.WhenAny(left.Task, Task.Delay(2500));
            await Task.Delay(300);                    // let the last message reach the engine
        }
        catch { }
        _closeReady = true;
        Close();
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        try { _web.Dispose(); } catch { }
        if (_engine.Owned) _engine.Stop();
        base.OnFormClosed(e);
    }
}

// ---------------------------------------------------------------------------------------------------- splash card
sealed class Splash : Form
{
    readonly System.Windows.Forms.Timer _timer = new() { Interval = 16 };
    readonly Image _logo;
    readonly Stopwatch _clock = Stopwatch.StartNew();
    string _status = "Starting...";
    bool _fadingOut;
    Font _title, _small;

    public Splash()
    {
        FormBorderStyle = FormBorderStyle.None;
        StartPosition = FormStartPosition.CenterScreen;
        ShowInTaskbar = true;
        Text = App.Name;
        Icon = App.LoadIcon();
        BackColor = App.Bg;
        DoubleBuffered = true;
        Opacity = 0;
        AutoScaleMode = AutoScaleMode.None;
        try { using var s = App.Resource("logo.png"); _logo = Image.FromStream(s); } catch { _logo = null; }
        _timer.Tick += (_, _) => Step();
    }

    protected override CreateParams CreateParams
    {
        get { var cp = base.CreateParams; cp.ClassStyle |= 0x20000; return cp; }   // CS_DROPSHADOW
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        float k = DeviceDpi / 96f;
        var area = Screen.FromPoint(Cursor.Position).WorkingArea;
        var size = new Size((int)(600 * k), (int)(360 * k));
        Bounds = new Rectangle(area.X + (area.Width - size.Width) / 2, area.Y + (area.Height - size.Height) / 2, size.Width, size.Height);
        Native.RoundCorners(Handle);
        _title = MakeFont(new[] { "Segoe UI Variable Display", "Segoe UI" }, 19f, FontStyle.Bold);
        _small = MakeFont(new[] { "Segoe UI Variable Text", "Segoe UI" }, 10f, FontStyle.Regular);
    }

    static Font MakeFont(string[] names, float pt, FontStyle st)
    {
        foreach (var n in names)
        {
            var f = new Font(n, pt, st);
            if (string.Equals(f.Name, n, StringComparison.OrdinalIgnoreCase)) return f;
            f.Dispose();
        }
        return new Font(FontFamily.GenericSansSerif, pt, st);
    }

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        _timer.Start();
    }

    public void SetStatus(string s)
    {
        if (IsDisposed) return;
        _status = s;
        Invalidate();
    }

    public void FadeOut() { if (IsDisposed) return; _fadingOut = true; if (!_timer.Enabled) _timer.Start(); }

    void Step()
    {
        if (_fadingOut)
        {
            Opacity = Math.Max(0, Opacity - 0.085);
            if (Opacity <= 0.01) { _timer.Stop(); Close(); return; }
        }
        else if (Opacity < 1) Opacity = Math.Min(1, Opacity + 0.1);
        if (Visible) Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
        float k = DeviceDpi / 96f, t = (float)_clock.Elapsed.TotalSeconds;
        var r = ClientRectangle;
        using (var bg = new LinearGradientBrush(r, Color.FromArgb(0x17, 0x11, 0x21), App.Bg, 90f)) g.FillRectangle(bg, r);
        // two soft glows drifting slowly behind the logo
        Glow(g, r.Width * (0.30f + 0.06f * MathF.Sin(t * 0.7f)), r.Height * (0.30f + 0.05f * MathF.Cos(t * 0.9f)), 260 * k, Color.FromArgb(70, App.Pink));
        Glow(g, r.Width * (0.72f + 0.05f * MathF.Cos(t * 0.6f)), r.Height * (0.55f + 0.06f * MathF.Sin(t * 0.8f)), 280 * k, Color.FromArgb(62, App.Purple));
        // hairline border
        using (var pen = new Pen(Color.FromArgb(40, 255, 255, 255), 1)) g.DrawRectangle(pen, 0, 0, r.Width - 1, r.Height - 1);

        // the logo, breathing gently
        float size = 118 * k * (1 + 0.022f * MathF.Sin(t * 2.2f));
        float cx = r.Width / 2f, top = 46 * k;
        if (_logo != null)
        {
            Glow(g, cx, top + 60 * k, 120 * k, Color.FromArgb(90, App.Pink));
            g.DrawImage(_logo, cx - size / 2, top + (118 * k - size) / 2, size, size);
        }
        using var center = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Near };
        using (var white = new SolidBrush(Color.FromArgb(0xf2, 0xee, 0xf8)))
            g.DrawString(App.Name, _title, white, new RectangleF(0, top + 132 * k, r.Width, 40 * k), center);
        using (var muted = new SolidBrush(App.Muted))
            g.DrawString(_status, _small, muted, new RectangleF(0, top + 176 * k, r.Width, 24 * k), center);

        // a thin bar with a pink-to-purple sweep running across it
        float bw = 240 * k, bh = 4 * k, bx = cx - bw / 2, by = r.Height - 58 * k;
        using (var track = RoundRect(bx, by, bw, bh, bh / 2))
        {
            using (var tb = new SolidBrush(Color.FromArgb(0x2a, 0x25, 0x35))) g.FillPath(tb, track);
            var old = g.Clip;
            g.SetClip(track);
            float sw = 110 * k, p = (t * 0.9f) % 1f;
            float sx = bx - sw + (bw + sw) * p;
            using (var sweep = new LinearGradientBrush(new RectangleF(sx - 1, by, sw + 2, bh), App.Pink, App.Purple, 0f))
            {
                sweep.InterpolationColors = new ColorBlend
                {
                    Colors = new[] { Color.FromArgb(0, App.Pink), App.Pink, App.Purple, Color.FromArgb(0, App.Purple) },
                    Positions = new[] { 0f, 0.35f, 0.7f, 1f },
                };
                g.FillRectangle(sweep, sx, by, sw, bh);
            }
            g.Clip = old;
        }
        using (var dim = new SolidBrush(Color.FromArgb(0x6b, 0x64, 0x78)))
        using (var right = new StringFormat { Alignment = StringAlignment.Far })
            g.DrawString("v" + App.Version + (App.Commit != null ? " \u00b7 " + App.Commit : ""), _small, dim, new RectangleF(0, r.Height - 30 * k, r.Width - 16 * k, 20 * k), right);
    }

    static void Glow(Graphics g, float x, float y, float radius, Color c)
    {
        using var path = new GraphicsPath();
        path.AddEllipse(x - radius, y - radius, radius * 2, radius * 2);
        using var b = new PathGradientBrush(path) { CenterColor = c, SurroundColors = new[] { Color.FromArgb(0, c) } };
        g.FillPath(b, path);
    }

    static GraphicsPath RoundRect(float x, float y, float w, float h, float rad)
    {
        var p = new GraphicsPath();
        float d = rad * 2;
        p.AddArc(x, y, d, d, 180, 90);
        p.AddArc(x + w - d, y, d, d, 270, 90);
        p.AddArc(x + w - d, y + h - d, d, d, 0, 90);
        p.AddArc(x, y + h - d, d, d, 90, 90);
        p.CloseFigure();
        return p;
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        _timer.Stop();
        base.OnFormClosed(e);
    }
}

// ---------------------------------------------------------------------------------------------------- window place
// Where the window was and whether it was maximized, so it opens the same way next time (maximized the first time).
static class Placement
{
    static readonly string FilePath = Path.Combine(App.DataDir, "window.txt");

    public static void Restore(Form f)
    {
        var area = (Screen.PrimaryScreen ?? Screen.AllScreens[0]).WorkingArea;
        f.Bounds = new Rectangle(area.X + area.Width / 10, area.Y + area.Height / 10, area.Width * 8 / 10, area.Height * 8 / 10);
        f.WindowState = FormWindowState.Maximized;
        try
        {
            var p = File.ReadAllText(FilePath).Trim().Split(' ').Select(int.Parse).ToArray();
            var b = new Rectangle(p[0], p[1], p[2], p[3]);
            if (b.Width >= 600 && b.Height >= 400 && Screen.AllScreens.Any(s => s.WorkingArea.IntersectsWith(b)))
            {
                f.Bounds = b;
                f.WindowState = p[4] == 1 ? FormWindowState.Maximized : FormWindowState.Normal;
            }
        }
        catch { /* first start */ }
    }

    public static void Save(Form f)
    {
        try
        {
            bool max = f.WindowState == FormWindowState.Maximized;
            if (f.WindowState == FormWindowState.Minimized && f.IsHandleCreated)
            {
                // minimized from maximized: open maximized next time
                var wp = new Native.WINDOWPLACEMENT { length = Marshal.SizeOf<Native.WINDOWPLACEMENT>() };
                if (Native.GetWindowPlacement(f.Handle, ref wp)) max = (wp.flags & 2) != 0;   // WPF_RESTORETOMAXIMIZED
            }
            var b = f.WindowState == FormWindowState.Normal ? f.Bounds : f.RestoreBounds;
            File.WriteAllText(FilePath, $"{b.X} {b.Y} {b.Width} {b.Height} {(max ? 1 : 0)}");
        }
        catch { }
    }
}

// ---------------------------------------------------------------------------------------------------- Windows calls
static class Native
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int RegisterWindowMessage(string name);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, int msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
    [DllImport("user32.dll")] public static extern bool AllowSetForegroundWindow(int pid);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr pid);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool attach);
    [DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetWindowPlacement(IntPtr h, ref WINDOWPLACEMENT wp);
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr CreateJobObject(IntPtr attrs, string name);
    [DllImport("kernel32.dll")] public static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint length);
    [DllImport("kernel32.dll")] public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("iphlpapi.dll")] static extern uint GetExtendedTcpTable(IntPtr table, ref int size, bool order, int af, int tableClass, int reserved);

    // Restore (if minimized) and bring a window to the front, even when another program has the foreground
    // (e.g. when the Sims Hub opened the animator).
    public static void BringToFront(IntPtr h)
    {
        if (IsIconic(h)) ShowWindow(h, 9);                                          // SW_RESTORE
        if (SetForegroundWindow(h)) return;
        var fg = GetForegroundWindow();
        uint fgThread = fg == IntPtr.Zero ? 0 : GetWindowThreadProcessId(fg, IntPtr.Zero), me = GetCurrentThreadId();
        if (fgThread != 0 && fgThread != me)
        {
            AttachThreadInput(me, fgThread, true);
            BringWindowToTop(h);
            SetForegroundWindow(h);
            AttachThreadInput(me, fgThread, false);
        }
    }

    // The process listening on 127.0.0.1:port (0 if none).
    public static int ListenerPid(int port)
    {
        int size = 0;
        GetExtendedTcpTable(IntPtr.Zero, ref size, false, 2, 3, 0);                 // AF_INET, TCP_TABLE_OWNER_PID_LISTENER
        IntPtr buf = Marshal.AllocHGlobal(size);
        try
        {
            if (GetExtendedTcpTable(buf, ref size, false, 2, 3, 0) != 0) return 0;
            int n = Marshal.ReadInt32(buf);
            for (int i = 0; i < n; i++)
            {
                IntPtr row = buf + 4 + i * 24;                                      // MIB_TCPROW_OWNER_PID: 6 x uint
                int localPort = ((Marshal.ReadByte(row, 8) << 8) | Marshal.ReadByte(row, 9));
                if (localPort == port) return Marshal.ReadInt32(row, 20);
            }
            return 0;
        }
        catch { return 0; }
        finally { Marshal.FreeHGlobal(buf); }
    }

    // A dark title bar in the app's own colour (Windows 11; older Windows just keeps its usual one).
    public static void StyleTitleBar(IntPtr h, Color caption)
    {
        int on = 1;
        DwmSetWindowAttribute(h, 20, ref on, 4);                                   // DWMWA_USE_IMMERSIVE_DARK_MODE
        int cap = caption.R | (caption.G << 8) | (caption.B << 16);
        DwmSetWindowAttribute(h, 35, ref cap, 4);                                  // DWMWA_CAPTION_COLOR
        int txt = 0xf2 | (0xee << 8) | (0xf8 << 16);
        DwmSetWindowAttribute(h, 36, ref txt, 4);                                  // DWMWA_TEXT_COLOR
    }

    public static void RoundCorners(IntPtr h)
    {
        int round = 2;                                                              // DWMWCP_ROUND
        DwmSetWindowAttribute(h, 33, ref round, 4);                                // DWMWA_WINDOW_CORNER_PREFERENCE
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct WINDOWPLACEMENT
    {
        public int length, flags, showCmd;
        public int minX, minY, maxX, maxY;
        public int left, top, right, bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_BASIC_LIMIT_INFORMATION
    {
        public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct IO_COUNTERS
    {
        public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount, ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }
}
