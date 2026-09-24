// Small things both apps need: error dialogs, opening links, downloads, and running programs without a window.
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Novulon.Desktop;

public static class Ui
{
    public static void OpenExternal(string uri)
    {
        try { Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true }); } catch { /* nothing to open it with */ }
    }

    public static void Fatal(string heading, string text, string logPath = null)
    {
        var page = new TaskDialogPage
        {
            Caption = Brand.Current.Name, Heading = heading, Text = text, Icon = TaskDialogIcon.Error,
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

    // For GitHub, python.org and Microsoft (never the app's own local server: that one goes without a proxy).
    public static HttpClient Web(TimeSpan timeout)
    {
        var http = new HttpClient(new SocketsHttpHandler
        {
            ConnectTimeout = TimeSpan.FromSeconds(10),
            AutomaticDecompression = DecompressionMethods.All,
        })
        { Timeout = timeout };
        http.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("Novulon", Brand.Current.Version));
        return http;
    }

    // A file from the web, saved next to where it goes (then moved into place: never half a file). progress: 0..1.
    public static async Task Download(HttpClient http, string url, string path, Action<double> progress = null)
    {
        using var r = await http.GetAsync(url, HttpCompletionOption.ResponseHeadersRead);
        r.EnsureSuccessStatusCode();
        long total = r.Content.Headers.ContentLength ?? -1, done = 0;
        var tmp = path + ".download";
        using (var from = await r.Content.ReadAsStreamAsync())
        using (var to = File.Create(tmp))
        {
            var buf = new byte[1 << 16];
            int n;
            while ((n = await from.ReadAsync(buf)) > 0)
            {
                await to.WriteAsync(buf.AsMemory(0, n));
                done += n;
                if (total > 0) progress?.Invoke((double)done / total);
            }
        }
        File.Move(tmp, path, true);
    }

    // Runs a program with no window and waits (at most `timeout`). Returns its exit code (-1: did not finish) and
    // everything it printed.
    public static (int Code, string Output) RunHidden(string exe, string[] args, TimeSpan timeout, string workDir = null)
    {
        var psi = new ProcessStartInfo(exe)
        {
            UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
        };
        if (workDir != null) psi.WorkingDirectory = workDir;
        foreach (var a in args) psi.ArgumentList.Add(a);
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        using var p = Process.Start(psi);
        var output = p.StandardOutput.ReadToEndAsync();
        var errors = p.StandardError.ReadToEndAsync();
        if (!p.WaitForExit((int)timeout.TotalMilliseconds))
        {
            try { p.Kill(true); } catch { }
            return (-1, "(did not finish in time)");
        }
        p.WaitForExit();
        return (p.ExitCode, output.Result + errors.Result);
    }

    public static void Log(string file, string line)
    {
        try
        {
            var path = Path.Combine(Brand.Current.DataDir, file);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            var fi = new FileInfo(path);
            if (fi.Exists && fi.Length > 500_000) File.Move(path, path + ".old", true);
            File.AppendAllText(path, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {line}\n");
        }
        catch { }
    }
}
