// The card shown while an app starts: its logo, name, what it is doing, and a running bar.
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

// ---------------------------------------------------------------------------------------------------- splash card
public sealed class Splash : Form
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
        Text = Brand.Current.Name;
        Icon = Brand.LoadIcon();
        BackColor = Brand.Current.Bg;
        DoubleBuffered = true;
        Opacity = 0;
        AutoScaleMode = AutoScaleMode.None;
        try { using var s = Brand.Resource("logo.png"); _logo = Image.FromStream(s); } catch { _logo = null; }
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
        using (var bg = new LinearGradientBrush(r, Color.FromArgb(0x17, 0x11, 0x21), Brand.Current.Bg, 90f)) g.FillRectangle(bg, r);
        // two soft glows drifting slowly behind the logo
        Glow(g, r.Width * (0.30f + 0.06f * MathF.Sin(t * 0.7f)), r.Height * (0.30f + 0.05f * MathF.Cos(t * 0.9f)), 260 * k, Color.FromArgb(70, Brand.Current.Accent));
        Glow(g, r.Width * (0.72f + 0.05f * MathF.Cos(t * 0.6f)), r.Height * (0.55f + 0.06f * MathF.Sin(t * 0.8f)), 280 * k, Color.FromArgb(62, Brand.Current.Accent2));
        // hairline border
        using (var pen = new Pen(Color.FromArgb(40, 255, 255, 255), 1)) g.DrawRectangle(pen, 0, 0, r.Width - 1, r.Height - 1);

        // the logo, breathing gently
        float size = 118 * k * (1 + 0.022f * MathF.Sin(t * 2.2f));
        float cx = r.Width / 2f, top = 46 * k;
        if (_logo != null)
        {
            Glow(g, cx, top + 60 * k, 120 * k, Color.FromArgb(90, Brand.Current.Accent));
            g.DrawImage(_logo, cx - size / 2, top + (118 * k - size) / 2, size, size);
        }
        using var center = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Near };
        using (var white = new SolidBrush(Color.FromArgb(0xf2, 0xee, 0xf8)))
            g.DrawString(Brand.Current.Name, _title, white, new RectangleF(0, top + 132 * k, r.Width, 40 * k), center);
        using (var muted = new SolidBrush(Brand.Current.Muted))
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
            using (var sweep = new LinearGradientBrush(new RectangleF(sx - 1, by, sw + 2, bh), Brand.Current.Accent, Brand.Current.Accent2, 0f))
            {
                sweep.InterpolationColors = new ColorBlend
                {
                    Colors = new[] { Color.FromArgb(0, Brand.Current.Accent), Brand.Current.Accent, Brand.Current.Accent2, Color.FromArgb(0, Brand.Current.Accent2) },
                    Positions = new[] { 0f, 0.35f, 0.7f, 1f },
                };
                g.FillRectangle(sweep, sx, by, sw, bh);
            }
            g.Clip = old;
        }
        using (var dim = new SolidBrush(Color.FromArgb(0x6b, 0x64, 0x78)))
        using (var right = new StringFormat { Alignment = StringAlignment.Far })
            g.DrawString("v" + Brand.Current.Version + (Brand.Current.Commit != null ? " \u00b7 " + Brand.Current.Commit : ""), _small, dim, new RectangleF(0, r.Height - 30 * k, r.Width - 16 * k, 20 * k), right);
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
