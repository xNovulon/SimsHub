using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Novulon.Desktop;

// ---------------------------------------------------------------------------------------------------- window place
// Where the window was and whether it was maximized, so it opens the same way next time (maximized the first time).
public static class Placement
{
    static string FilePath => Path.Combine(Brand.Current.DataDir, "window.txt");

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
