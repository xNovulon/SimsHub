// Novulon's Wicked Animator - the desktop app.
//
// A real Windows window (Microsoft Edge WebView2) around the animator, and its engine - the local server in
// backend\server.py - started quietly in the background: no console window, no browser. Closing the window first has
// the page write any unfinished work to the recovery file, then stops the engine (only if this window started it).
// Opening the app again while it is open brings the open window to the front; opening it while it is still closing
// waits for that and then opens it fresh.
//
// This program is all anyone needs to download: opened from anywhere, it installs the animator in
// %USERPROFILE%\Tools\sims4_animator with its shortcuts; every start brings it up to date from GitHub and gets what it
// runs on ready - Python and its packages, WebView2 (the parts both Novulon apps share: ..\..\shared\desktop).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using Novulon.Desktop;

// The update marker (Brand.Marker) also goes in the program's version details: the only text Windows keeps
// uncompressed in the program file, where an update checks for it (Updater.cs).
[assembly: System.Reflection.AssemblyTrademark("Novulon.WickedAnimator.AutoUpdate.v1")]

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
    public static string Root;              // the animator's folder (web\ and backend\), once Setup has found it
    const string MutexName = @"Local\Novulon.WickedAnimator";
    const string ClosingName = @"Local\Novulon.WickedAnimator.Closing";
    static EventWaitHandle _closing;

    // the page's colours (web/css/app.css)
    public static readonly Color Bg = Color.FromArgb(0x0b, 0x0a, 0x10);
    public static readonly Color Pink = Color.FromArgb(0xff, 0x4f, 0x9a);
    public static readonly Color Purple = Color.FromArgb(0x8b, 0x5c, 0xf6);
    public static readonly Color Muted = Color.FromArgb(0xa7, 0x9f, 0xb8);

    static readonly Brand Brand = new()
    {
        Name = Name, Version = Version, DataDir = DataDir,
        InstallDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Tools", "sims4_animator"),
        ExeName = "Wicked Animator.exe",
        DesktopShortcut = "Wicked Animator", StartMenuShortcut = "Novulon's Wicked Animator",
        Description = "Novulon's Wicked Animator - make WickedWhims animations without Blender",
        IsAppFolder = d => File.Exists(Path.Combine(d, "backend", "server.py")) && Directory.Exists(Path.Combine(d, "web")),
        RepoFolder = "wicked_animator/", ReleaseAsset = "WickedAnimator.exe",
        Marker = "Novulon.WickedAnimator.AutoUpdate.v1",               // keep it the same as the AssemblyTrademark above
        Skip = new[] { "desktop/", "tools/" },          // the program's source and the developers' checks
        PythonCheck = "import numpy, PIL, google.protobuf",
        PythonPackages = new[] { "numpy", "Pillow", "protobuf", "soundfile" },
        Bg = Bg, Accent = Pink, Accent2 = Purple, Muted = Muted,
    };

    [STAThread]
    static void Main(string[] args)
    {
        Novulon.Desktop.Brand.Use(Brand);
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
        Setup.RunLaunch(args);                            // the installed or updated program, when Setup named one
    }

    // the window is hidden and saving: a copy opened now waits for it instead of doing nothing
    public static void MarkClosing() { try { _closing?.Set(); } catch { } }

    public static void OpenExternal(string uri) => Ui.OpenExternal(uri);

    public static void Fatal(string heading, string text, string logPath = null) => Ui.Fatal(heading, text, logPath);
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

    Process _proc;
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

    public void Start(PythonSetup.Python py)
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
        try { Native.EndWithThisProcess(p); }
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
    PythonSetup.Python _python;
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
        Icon = Brand.LoadIcon();
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
            // 0. installed and up to date (Setup.cs, Updater.cs: quick when there is nothing new, skipped offline)
            Action<string> say = s => { try { _splash.BeginInvoke(new Action(() => _splash.SetStatus(s))); } catch { } };
            var ready = await Setup.Prepare(say);
            if (_abandoned || IsDisposed) return;
            if (ready.Failed) { Quit(); return; }
            if (ready.Launch != null)
            {
                Setup.SetLaunch(ready.Launch);           // Main opens it once this program has ended
                Quit(); return;
            }
            App.Root = ready.Root;

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
                _python = await PythonSetup.Ensure(say);
                if (_python == null) { NoPython(); return; }
                _engine.Start(_python);
                _waiting = true;
                try { if (!await WaitForEngine()) return; } finally { _waiting = false; }
            }

            // 2. the window's web view
            _splash.SetStatus("Opening the stage...");
            var env = _env = await CreateEnvironment(say);
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

    async Task<CoreWebView2Environment> CreateEnvironment(Action<string> say)
    {
        try
        {
            // sounds may play without a click first - this is an app, not a web page. On PCs with two graphics
            // chips (a laptop's built-in one and a gaming one) the 3D view and motion capture use the faster one.
            var args = "--autoplay-policy=no-user-gesture-required --force_high_performance_gpu";
            // automated tests can drive the window (WICKED_DEBUG_PORT=9229)
            var debugPort = Environment.GetEnvironmentVariable("WICKED_DEBUG_PORT");
            if (int.TryParse(debugPort, out int dp) && dp > 1024) args += $" --remote-debugging-port={dp}";
            return await WebViewHost.Create(args, say);        // installs WebView2 first on a PC without it
        }
        catch (WebView2RuntimeNotFoundException)
        {
            HideSplash();
            var page = new TaskDialogPage
            {
                Caption = App.Name, Icon = TaskDialogIcon.Warning,
                Heading = "Microsoft Edge WebView2 is needed",
                Text = "The animator's window needs Microsoft Edge WebView2 (free, from Microsoft), and it could not be installed "
                     + "by itself. Click \"Get WebView2\", open the file it downloads (MicrosoftEdgeWebview2Setup.exe) to install it, "
                     + "then open the animator again.",
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
        WebViewHost.AppMenus(w);                     // no browser right-click menu; right-drag looks around, the app has its own menus
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
        _ = w.AddScriptToExecuteOnDocumentCreatedAsync($"window.wickedDesktop = {{ version: '{App.Version}', commit: '{Novulon.Desktop.Brand.Current.Commit ?? ""}' }};");

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
        if (_python == null) _python = await Task.Run(PythonSetup.Find);   // the engine was one this window reused
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
            Text = "The animator's engine runs on Python 3 (free), and it could not be installed by itself - check the internet "
                 + "connection and open the animator again. Or install Python 3.12 or newer from python.org (tick \"Add python.exe to "
                 + "PATH\"), then open the animator again.",
        };
        var get = new TaskDialogButton("Get Python");
        var log = new TaskDialogButton("Open the log");
        page.Buttons.Add(get);
        if (File.Exists(PythonSetup.LogPath)) page.Buttons.Add(log);
        page.Buttons.Add(TaskDialogButton.Close);
        var pick = TaskDialog.ShowDialog(page);
        if (pick == get) App.OpenExternal("https://www.python.org/downloads/windows/");
        else if (pick == log) App.OpenExternal(PythonSetup.LogPath);
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
