// The window's web view (Microsoft Edge WebView2): its loader, which travels inside the program, and the WebView2
// runtime itself - part of Windows 11; on a PC without it, Microsoft's installer is downloaded and run quietly (for
// this Windows user; no administrator needed) before the window opens.
using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Web.WebView2.Core;

namespace Novulon.Desktop;

public static class WebViewHost
{
    const string LoaderVersion = "1.0.3179.45";
    const string RuntimeSetupUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703";   // Microsoft's Evergreen bootstrapper
    static bool _loaderSet;

    // Right-click like a program, not a browser: no browser menu anywhere ("Open link in new window", "Save link
    // as"...); in a text box only Cut, Copy, Paste and Select all. The page's own menus (the animator's timeline and
    // bones) still open: they handle the right-click before this is asked.
    static readonly string[] TextMenu = { "cut", "copy", "paste", "selectAll" };

    public static void AppMenus(CoreWebView2 w)
    {
        w.Settings.AreDefaultContextMenusEnabled = true;
        w.ContextMenuRequested += (_, e) =>
        {
            if (!e.ContextMenuTarget.IsEditable)
            {
                e.Handled = true;
                return;
            }
            foreach (var item in e.MenuItems.ToList())
                if (!TextMenu.Contains(item.Name)) e.MenuItems.Remove(item);
            while (e.MenuItems.Count > 0 && e.MenuItems[0].Kind == CoreWebView2ContextMenuItemKind.Separator) e.MenuItems.RemoveAt(0);
            if (e.MenuItems.Count == 0) e.Handled = true;
        };
    }

    // A file the page saves (e.g. "Share my poses") goes straight to the Downloads folder, as the page says, without
    // the browser's download panel.
    public static void QuietDownloads(CoreWebView2 w)
    {
        w.DownloadStarting += (_, e) => { e.Handled = true; };
    }

    // Throws WebView2RuntimeNotFoundException when the runtime is missing and could not be installed.
    public static async Task<CoreWebView2Environment> Create(string browserArgs, Action<string> status)
    {
        SetLoader();
        if (!RuntimeInstalled())
        {
            status("Installing WebView2...");
            await InstallRuntime(status);
            if (!RuntimeInstalled()) throw new WebView2RuntimeNotFoundException();
        }
        var opts = new CoreWebView2EnvironmentOptions(browserArgs);
        return await CoreWebView2Environment.CreateAsync(null, Path.Combine(Brand.Current.DataDir, "WebView2"), opts);
    }

    // WebView2Loader.dll is written next to the window's data once, from inside the program
    static void SetLoader()
    {
        if (_loaderSet) return;
        var dir = Path.Combine(Brand.Current.DataDir, "runtime", LoaderVersion);
        var dll = Path.Combine(dir, "WebView2Loader.dll");
        using (var s = Brand.Resource("WebView2Loader.dll"))
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
        _loaderSet = true;
    }

    static bool RuntimeInstalled()
    {
        try { return !string.IsNullOrEmpty(CoreWebView2Environment.GetAvailableBrowserVersionString()); }
        catch (WebView2RuntimeNotFoundException) { return false; }
    }

    static async Task InstallRuntime(Action<string> status)
    {
        var setup = Path.Combine(Path.GetTempPath(), "MicrosoftEdgeWebview2Setup.exe");
        try
        {
            using var http = Ui.Web(TimeSpan.FromMinutes(10));
            await Ui.Download(http, RuntimeSetupUrl, setup);
            var r = await Task.Run(() => Ui.RunHidden(setup, new[] { "/silent", "/install" }, TimeSpan.FromMinutes(10)));
            Ui.Log("setup.log", $"WebView2 installer exit {r.Code}");
        }
        catch (Exception ex) { Ui.Log("setup.log", "WebView2 installer: " + ex.Message); }
        finally { try { File.Delete(setup); } catch { } }
    }
}
