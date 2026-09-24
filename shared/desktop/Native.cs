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

// ---------------------------------------------------------------------------------------------------- Windows calls
public static class Native
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

    // A program this one starts (an app's engine) lives only as long as this one: if the app is closed or crashes,
    // Windows ends it too. Programs it opens in turn (Explorer "show in folder") are not part of it.
    static IntPtr _job;
    public static void EndWithThisProcess(Process p)
    {
        if (_job == IntPtr.Zero)
        {
            _job = CreateJobObject(IntPtr.Zero, null);
            var info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
            info.BasicLimitInformation.LimitFlags = 0x2000 | 0x1000;   // kill on close | breakaway OK
            int size = Marshal.SizeOf(info);
            IntPtr ptr = Marshal.AllocHGlobal(size);
            try
            {
                Marshal.StructureToPtr(info, ptr, false);
                SetInformationJobObject(_job, 9, ptr, (uint)size);
            }
            finally { Marshal.FreeHGlobal(ptr); }
        }
        AssignProcessToJobObject(_job, p.Handle);
    }

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
