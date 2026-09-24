// What makes each Novulon app itself - its name, look, folder on GitHub and place on the PC - for the parts both
// desktop apps share (this folder). Each app's Program.cs fills one in and calls Brand.Use first thing.
using System;
using System.Drawing;
using System.IO;
using System.Reflection;

namespace Novulon.Desktop;

public sealed class Brand
{
    public static Brand Current { get; private set; }
    public static void Use(Brand brand) => Current = brand;

    public string Name { get; init; }            // "Novulon's Wicked Animator"
    public string Version { get; init; }         // shown on the splash card
    public string DataDir { get; init; }         // %LOCALAPPDATA%\... - logs, window place, update state
    public string InstallDir { get; init; }      // where the app lives on the PC (a download installs it here)
    public string ExeName { get; init; }         // the program's file name in InstallDir
    public string DesktopShortcut { get; init; } // shortcut names (without .lnk)
    public string StartMenuShortcut { get; init; }
    public string Description { get; init; }     // the shortcuts' tooltip
    public Func<string, bool> IsAppFolder { get; init; }   // does this folder hold the app's files?

    // GitHub: the app's folder in the repository, and its program in the "apps" release
    public string RepoFolder { get; init; }      // "wicked_animator/"
    public string ReleaseAsset { get; init; }    // "WickedAnimator.exe"
    // Every program of this app that can update itself carries this text; a download without it is never put in
    // place (it could never update again). Keep it the same in every version.
    public string Marker { get; init; }
    // Files the app never needs on a PC (sources, tests, research): not downloaded. Keep: exceptions inside them.
    public string[] Skip { get; init; } = Array.Empty<string>();
    public string[] Keep { get; init; } = Array.Empty<string>();

    // Python: code that must run for the app's engine to start, and the pip packages that provide it
    public string PythonCheck { get; init; }
    public string[] PythonPackages { get; init; } = Array.Empty<string>();

    // the look (the page's own colours)
    public Color Bg { get; init; }
    public Color Accent { get; init; }
    public Color Accent2 { get; init; }
    public Color Muted { get; init; }

    public string Commit { get; set; }           // the GitHub version the app's folder has (short), when known

    public static Stream Resource(string name) => Assembly.GetEntryAssembly()?.GetManifestResourceStream(name);

    public static Icon LoadIcon()
    {
        try { using var s = Resource("logo.ico"); return new Icon(s); } catch { return null; }
    }

    public bool Wanted(string rel)
    {
        foreach (var k in Keep) if (rel == k) return true;
        foreach (var s in Skip) if (rel == s || (s.EndsWith("/") && rel.StartsWith(s, StringComparison.Ordinal))) return false;
        return true;
    }
}
