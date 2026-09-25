// Novulon's Sims Hub - the desktop app.
//
// A real Windows window (Microsoft Edge WebView2) around the Hub, and its engine - the local server in
// speedkit\hub\server.py - started quietly in the background: no console window, no browser. Opening the app again
// while it is open brings the open window to the front. Closing the window stops the engine; while the engine is still
// busy (merging, cleaning up, switching modes) it finishes first, out of sight, and then stops.
//
// This program is all anyone needs to download: opened from anywhere, it installs the Hub in
// %USERPROFILE%\Tools\sims4_speedkit with its shortcuts; every start brings it up to date from GitHub and gets what it
// runs on ready - Python and numpy, WebView2 (the parts both Novulon apps share: ..\..\shared\desktop).
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net.Http;
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
[assembly: System.Reflection.AssemblyTrademark("Novulon.SimsHub.AutoUpdate.v1")]

namespace SimsHub;

static class App
{
    public const string Name = "Novulon's Sims Hub";
    public const string Version = "1.0.0";
    public const int Port = 8766;
    public static readonly string Url = $"http://127.0.0.1:{Port}/";
    public static readonly string DataDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NovulonSimsHub");
    public static int ShowMessage;          // a second copy asks the open window to come to the front
    public static string Root;              // the Hub's folder (speedkit\), once Setup has found it
    const string MutexName = @"Local\Novulon.SimsHub";

    // the page's colours (speedkit/hub/web/css/hub.css)
    public static readonly Color Bg = Color.FromArgb(0x0b, 0x0a, 0x10);

    static readonly Brand Brand = new()
    {
        Name = Name, Version = Version, DataDir = DataDir,
        InstallDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Tools", "sims4_speedkit"),
        ExeName = "Sims Hub.exe",
        DesktopShortcut = Name, StartMenuShortcut = Name,
        Description = "Novulon's Sims Hub - fast loading, lag fixes and tidy mods for The Sims 4",
        IsAppFolder = d => File.Exists(Path.Combine(d, "speedkit", "hub", "server.py")),
        RepoFolder = "sims_hub/", ReleaseAsset = "SimsHub.exe",
        Marker = "Novulon.SimsHub.AutoUpdate.v1",               // keep it the same as the AssemblyTrademark above
        // the program's source, tests, research notes and artwork: developers only. The Hub reads one research file.
        Skip = new[] { "desktop/", "tests/", "research/", "branding/", "docs/" },
        Keep = new[] { "research/merging/companions.json" },
        PythonCheck = "import numpy",
        PythonPackages = new[] { "numpy" },
        Bg = Bg,
        Accent = Color.FromArgb(0xff, 0x4f, 0x9a),
        Accent2 = Color.FromArgb(0xa8, 0x55, 0xf7),
        Muted = Color.FromArgb(0xa3, 0x9b, 0xb2),
    };

    [STAThread]
    static void Main(string[] args)
    {
        Novulon.Desktop.Brand.Use(Brand);
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        Application.EnableVisualStyles();                 // before any dialog (TaskDialog needs them)
        Application.SetCompatibleTextRenderingDefault(false);
        ShowMessage = Native.RegisterWindowMessage("Novulon.SimsHub.Show");
        if (Setup.FinishUpdate(args)) return;             // a new program putting itself in place after an update

        var single = new Mutex(true, MutexName, out bool owned);
        if (!owned && Setup.EndStaleCopy())
        {
            try { owned = single.WaitOne(TimeSpan.FromSeconds(5)); }
            catch (AbandonedMutexException) { owned = true; }
        }
        if (!owned)
        {
            // already open: bring that window to the front (and let it take the foreground)
            Native.AllowSetForegroundWindow(-1);
            Native.PostMessage((IntPtr)0xffff, ShowMessage, IntPtr.Zero, IntPtr.Zero);   // HWND_BROADCAST
            single.Dispose();
            return;
        }
        try
        {
            Directory.CreateDirectory(DataDir);
            Application.ThreadException += (_, e) => Ui.Fatal("Something went wrong", e.Exception.Message);
            Application.Run(new Launcher(args));
        }
        finally
        {
            try { single.ReleaseMutex(); } catch { }
            single.Dispose();
        }
        Setup.RunLaunch(args);                            // the installed or updated program, when Setup named one
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
// The Python server (python -m speedkit.hub --serve), run without a console window. Its output goes to engine.log.
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
    public event Action<int> Exited;           // exit code (the engine stopped by itself)

    public bool Owned => _proc != null;
    public bool Running { get { try { return _proc != null && !_proc.HasExited; } catch { return false; } } }

    // What answers on the Hub's port: Kind "ok" (the Hub: its pid and whether a task runs), "other" (another program),
    // or null (nothing yet).
    public record Status(string Kind, int Pid, bool Busy);

    public static async Task<Status> StatusAsync()
    {
        try
        {
            using var r = await Http.GetAsync(App.Url + "api/ping");
            var body = await r.Content.ReadAsStringAsync();
            try
            {
                using var j = JsonDocument.Parse(body);
                var e = j.RootElement;
                if (e.TryGetProperty("app", out var app) && app.GetString() == App.Name)
                    return new Status("ok",
                        e.TryGetProperty("pid", out var p) && p.ValueKind == JsonValueKind.Number ? p.GetInt32() : 0,
                        e.TryGetProperty("busy", out var b) && b.ValueKind == JsonValueKind.True);
            }
            catch (JsonException) { }
            return new Status("other", 0, false);
        }
        catch (HttpRequestException) { return null; }
        catch (TaskCanceledException) { return null; }
    }

    // A Hub left running from before (started by the old Desktop shortcut, or older code): stopped, so this window's
    // own starts with the newest code. Only a Python process is ever stopped.
    public static async Task<bool> StopOther(int pid)
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
            if (await StatusAsync() == null) return true;
            await Task.Delay(100);
        }
        return false;
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
        foreach (var a in new[] { "-u", "-m", "speedkit.hub", "--serve", "--port", App.Port.ToString() }) psi.ArgumentList.Add(a);
        var path = psi.Environment.TryGetValue("PYTHONPATH", out var pp) && !string.IsNullOrEmpty(pp) ? App.Root + ";" + pp : App.Root;
        psi.Environment["PYTHONPATH"] = path;
        psi.Environment["PYTHONIOENCODING"] = "utf-8";    // names in any language print fine into the log
        psi.Environment["PYTHONUTF8"] = "1";
        psi.Environment["SIMS_HUB_NO_UPDATE"] = "1";      // this program keeps the Hub up to date
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
        try { Native.EndWithThisProcess(proc); }
        catch (Exception ex) { Log("(could not tie the engine to the window: " + ex.Message + ")"); }
        proc.BeginOutputReadLine();
        proc.BeginErrorReadLine();
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
    PythonSetup.Python _python;
    bool _closing, _shown, _waiting, _abandoned;
    public bool Starting = true;
    int _restarts;
    DateTime _firstRestart;

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
        _engine.Exited += code => { try { if (!IsDisposed) BeginInvoke(new Action(() => EngineStopped(code))); } catch { } };
        CreateHandle();                               // hidden until the page has loaded
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        Native.StyleTitleBar(Handle, Color.FromArgb(0x12, 0x10, 0x19));
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
        if (keyData == Keys.F12 && _devtools) { _web.CoreWebView2?.OpenDevToolsWindow(); return true; }
        return base.ProcessCmdKey(ref msg, keyData);
    }

    void HideSplash() { if (!_splash.IsDisposed) _splash.Hide(); }

    // The user closed the splash card while starting: end quietly.
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
                Setup.SetLaunch(ready);                  // Main opens it once this program has ended
                Quit(); return;
            }
            App.Root = ready.Root;

            // 1. the engine: a Hub left running from before is replaced by this window's own - unless it is busy
            var status = await Engine.StatusAsync();
            if (status?.Kind == "other")
            {
                HideSplash();
                Ui.Fatal("Another program is using the Hub's port",
                    $"Something else on this PC answers at {App.Url}. Close it (or restart the PC) and open the Hub again.");
                Quit(); return;
            }
            if (status?.Kind == "ok" && !status.Busy && await Engine.StopOther(status.Pid)) status = null;
            if (status == null)
            {
                say("Starting the Hub...");
                _python = await PythonSetup.Ensure(say);
                if (_abandoned || IsDisposed) return;
                if (_python == null) { NoPython(); return; }
                say("Starting the Hub...");
                _engine.Start(_python);
                _waiting = true;
                try { if (!await WaitForEngine()) return; } finally { _waiting = false; }
            }

            // 2. the window's web view (WebView2 is installed first on a PC without it)
            say("Opening the Hub...");
            var env = await WebViewHost.Create("", say);
            _ = _web.Handle;                // the view needs its handle (the window stays hidden until loaded)
            await _web.EnsureCoreWebView2Async(env);
            Configure(_web.CoreWebView2);
            _web.CoreWebView2.Navigate(App.Url);
        }
        catch (WebView2RuntimeNotFoundException)
        {
            HideSplash();
            var page = new TaskDialogPage
            {
                Caption = App.Name, Icon = TaskDialogIcon.Warning,
                Heading = "Microsoft Edge WebView2 is needed",
                Text = "The Hub's window needs Microsoft Edge WebView2 (free, from Microsoft), and it could not be installed by itself. "
                     + "Click \"Get WebView2\", open the file it downloads to install it, then open the Hub again.",
            };
            var get = new TaskDialogButton("Get WebView2");
            page.Buttons.Add(get);
            page.Buttons.Add(TaskDialogButton.Close);
            if (TaskDialog.ShowDialog(page) == get) Ui.OpenExternal("https://go.microsoft.com/fwlink/p/?LinkId=2124703");
            Quit();
        }
        catch (Exception ex)
        {
            if (_abandoned || _closing || IsDisposed) return;
            HideSplash();
            Ui.Fatal("The Hub could not start", ex.Message, Engine.LogPath);
            Quit();
        }
    }

    async Task<bool> WaitForEngine()
    {
        var t0 = DateTime.Now;
        while (true)
        {
            await Task.Delay(150);
            if ((await Engine.StatusAsync())?.Kind == "ok") return true;
            if (_abandoned || IsDisposed) return false;
            if (!_engine.Running) { EngineFailed("The Hub's engine stopped while starting."); return false; }
            if ((DateTime.Now - t0).TotalSeconds > 90) { EngineFailed("The Hub's engine did not answer in time."); return false; }
        }
    }

    void Configure(CoreWebView2 w)
    {
        var s = w.Settings;
        s.AreDevToolsEnabled = _devtools;
        s.IsStatusBarEnabled = false;
        s.IsZoomControlEnabled = false;
        s.AreBrowserAcceleratorKeysEnabled = false;  // no print/reload - the page's own shortcuts still work
        s.IsPasswordAutosaveEnabled = false;
        s.IsGeneralAutofillEnabled = false;
        s.IsSwipeNavigationEnabled = false;
        s.IsPinchZoomEnabled = false;                // a touchpad pinch must not zoom the whole app
        s.IsBuiltInErrorPageEnabled = false;
        WebViewHost.AppMenus(w);                     // no browser right-click menu
        _web.AllowExternalDrop = false;
        _ = w.AddScriptToExecuteOnDocumentCreatedAsync(
            $"window.novulonDesktop = {{ app: 'hub', version: '{App.Version}', commit: '{Brand.Current.Commit ?? ""}' }};");

        w.NavigationStarting += (_, e) =>
        {
            if (IsOwn(e.Uri) || e.Uri == "about:blank") return;
            e.Cancel = true;                          // links to the web open in the normal browser
            if (e.Uri.StartsWith("http", StringComparison.OrdinalIgnoreCase) || e.Uri.StartsWith("mailto:", StringComparison.OrdinalIgnoreCase))
                Ui.OpenExternal(e.Uri);
        };
        w.NewWindowRequested += (_, e) =>
        {
            e.Handled = true;
            if (e.Uri.StartsWith("http", StringComparison.OrdinalIgnoreCase)) Ui.OpenExternal(e.Uri);
        };
        w.PermissionRequested += (_, e) =>
            e.State = IsOwn(e.Uri) ? CoreWebView2PermissionState.Allow : CoreWebView2PermissionState.Deny;
        w.DocumentTitleChanged += (_, _) =>
        {
            var t = w.DocumentTitle;
            Text = string.IsNullOrWhiteSpace(t) || t.StartsWith("127.0.0.1") ? App.Name : t;
        };
        w.NavigationCompleted += async (_, e) =>
        {
            if (_closing) return;
            if (!e.IsSuccess)
            {
                if (e.WebErrorStatus == CoreWebView2WebErrorStatus.OperationCanceled) return;
                if (!_shown && e.HttpStatusCode >= 400)
                {
                    EngineFailed($"The Hub's page could not be opened (error {e.HttpStatusCode}).");
                    return;
                }
                await Task.Delay(800);                // the engine may be restarting: try again shortly
                if (!_closing) w.Navigate(App.Url);
                return;
            }
            if (!_shown && IsOwn(w.Source)) Reveal();
        };
        w.ProcessFailed += async (_, e) =>
        {
            if (_closing) return;
            _engine.Log($"(window process failed: {e.ProcessFailedKind})");
            if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessExited)
            {
                await Task.Delay(300);
                try { w.Reload(); } catch { }
            }
        };
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
        if (WindowState == FormWindowState.Minimized && want != FormWindowState.Minimized) WindowState = want;
        Native.BringToFront(Handle);
        _web.Focus();
        _splash.FadeOut();
    }

    // -------------------------------------------------------------- the engine stopping / not found
    async void EngineStopped(int code)
    {
        if (_closing || _waiting) return;             // WaitForEngine reports a stop while starting
        // stopped while in use: start it again (the page waits a moment and reconnects)
        if ((DateTime.Now - _firstRestart).TotalMinutes > 2) { _firstRestart = DateTime.Now; _restarts = 0; }
        if (_python == null) _python = await Task.Run(PythonSetup.Find);
        if (_closing) return;
        if (_python != null && _restarts++ < 3)
        {
            try { _engine.Start(_python); return; } catch (Exception ex) { _engine.Log("restart failed: " + ex.Message); }
        }
        if (!_shown) { EngineFailed("The Hub's engine stopped while starting."); return; }
        Ui.Fatal("The Hub's engine keeps stopping",
            "Close the Hub and open it again.\n\nLast messages:\n" + Engine.LogTail(8), Engine.LogPath);
    }

    void EngineFailed(string what)
    {
        _engine.Stop();
        var tail = Engine.LogTail();
        var hint = tail.Contains("No module named") ? "\n\nA Python part is missing - see the log."
                 : tail.Contains("in use") ? $"\n\nPort {App.Port} is in use by another program."
                 : "";
        HideSplash();
        Ui.Fatal(what, "Last messages from the engine:\n" + (tail.Length > 0 ? tail : "(none)") + hint, Engine.LogPath);
        Quit();
    }

    void NoPython()
    {
        HideSplash();
        var page = new TaskDialogPage
        {
            Caption = App.Name, Icon = TaskDialogIcon.Warning,
            Heading = "Python is needed",
            Text = "The Hub's engine runs on Python 3 (free), and it could not be installed by itself - check the internet "
                 + "connection and open the Hub again. Or install Python 3.12 or newer from python.org (tick \"Add python.exe to "
                 + "PATH\"), then open the Hub again.",
        };
        var get = new TaskDialogButton("Get Python");
        var log = new TaskDialogButton("Open the log");
        page.Buttons.Add(get);
        if (File.Exists(PythonSetup.LogPath)) page.Buttons.Add(log);
        page.Buttons.Add(TaskDialogButton.Close);
        var pick = TaskDialog.ShowDialog(page);
        if (pick == get) Ui.OpenExternal("https://www.python.org/downloads/windows/");
        else if (pick == log) Ui.OpenExternal(PythonSetup.LogPath);
        Quit();
    }

    // -------------------------------------------------------------- closing
    // A task still running (merging, cleaning up, switching modes) is never cut short: the window goes, the engine
    // finishes out of sight and then stops, and this program ends with it.
    protected override async void OnFormClosing(FormClosingEventArgs e)
    {
        if (_closing || !_shown || !_engine.Owned || e.CloseReason == CloseReason.WindowsShutDown)
        {
            if (_shown) Placement.Save(this);
            base.OnFormClosing(e);
            return;
        }
        e.Cancel = true;                              // decided below (after the first await it would be too late)
        _closing = true;
        Placement.Save(this);
        if ((await Engine.StatusAsync())?.Busy == true)
        {
            var page = new TaskDialogPage
            {
                Caption = App.Name, Icon = TaskDialogIcon.Information,
                Heading = "The Hub is still working",
                Text = "It finishes what it is doing in the background, then closes by itself. Don't start the game until then.",
                Buttons = { TaskDialogButton.OK },
            };
            TaskDialog.ShowDialog(this, page);
            Hide();
            while ((await Engine.StatusAsync())?.Busy == true) await Task.Delay(2000);
        }
        Close();                                      // _closing: this time it closes
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        try { _web.Dispose(); } catch { }
        if (_engine.Owned) _engine.Stop();
        base.OnFormClosed(e);
    }
}
