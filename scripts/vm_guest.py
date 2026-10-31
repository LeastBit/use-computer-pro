# -*- coding: utf-8 -*-
"""vmrun helper: run scripts inside a VMware guest and pull results / screenshots back.

Usage:
  python vm_guest.py --vmx <path.vmx> list
  python vm_guest.py --vmx ... --gu u --gp p exec --script ./task.sh [--out ./result.txt] [--arg x]
  python vm_guest.py --vmx ... --gu u --gp p shot --out ./guest.png [--os linux|windows]
  python vm_guest.py --vmx ... --gu u --gp p put --local a.txt --remote /tmp/a.txt
  python vm_guest.py --vmx ... --gu u --gp p get --remote /tmp/a.txt --local a.txt

Notes:
  * guest operations require VMware Tools / open-vm-tools
  * GUI programs launched via runProgramInGuest return immediately -> write to a file
  * a halted guest makes captureScreen hang: every call here has a hard timeout
  * vmrun global options (-gu/-gp) must come BEFORE the command name
"""
import argparse, os, subprocess, sys, tempfile

VMRUN = os.environ.get("VMRUN", r"D:\app\VMware\VMware Workstation\vmrun.exe")
DEFAULT_TIMEOUT = int(os.environ.get("VMRUN_TIMEOUT", "120"))


def run(args, timeout):
    cmd = [VMRUN, "-T", "ws"] + args
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        raw = (p.stdout or b"") + (p.stderr or b"")
        text = None
        for enc in ("utf-8", "gbk", "mbcs"):
            try:
                text = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        return p.returncode, (text or raw.decode("utf-8", "replace")).strip()
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT after %ss" % timeout
    except FileNotFoundError:
        return -2, "vmrun not found: %s" % VMRUN


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vmx", required=True)
    ap.add_argument("--gu", default=None, help="guest user")
    ap.add_argument("--gp", default=None, help="guest password")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    p_exec = sub.add_parser("exec")
    p_exec.add_argument("--script", required=True)
    p_exec.add_argument("--interpreter", default="/bin/bash")
    p_exec.add_argument("--out", default="guest_out.txt")
    p_exec.add_argument("--arg", default="")

    p_shot = sub.add_parser("shot")
    p_shot.add_argument("--out", required=True)
    p_shot.add_argument("--os", choices=["linux", "windows"], default="linux")

    p_put = sub.add_parser("put")
    p_put.add_argument("--local", required=True)
    p_put.add_argument("--remote", required=True)

    p_get = sub.add_parser("get")
    p_get.add_argument("--remote", required=True)
    p_get.add_argument("--local", required=True)

    a = ap.parse_args()
    T = a.timeout

    if a.cmd == "list":
        rc, out = run(["list"], T)
        print(out)
        return 0 if rc == 0 else 1

    if not a.gu or not a.gp:
        print("--gu / --gp are required for guest operations")
        return 2

    def g(cmdname, *rest):
        return ["-gu", a.gu, "-gp", a.gp, cmdname, a.vmx] + list(rest)

    if a.cmd == "exec":
        remote = "/tmp/agent_run.sh"
        rc, out = run(g("copyFileFromHostToGuest", os.path.abspath(a.script), remote), T)
        if rc != 0:
            print("copy-in failed:", out)
            return 3
        wrapper = "/tmp/agent_wrap.sh"
        body = ("#!/bin/bash\n"
                "export DISPLAY=:0\n"
                "export XAUTHORITY=/home/%s/.Xauthority\n"
                "%s %s %s > /tmp/agent_out.txt 2>&1\n"
                "echo \"__rc=$?\" >> /tmp/agent_out.txt\nexit 0\n"
                % (a.gu, a.interpreter, remote, a.arg))
        local_wrap = os.path.join(tempfile.gettempdir(), "agent_wrap.sh")
        with open(local_wrap, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        rc, out = run(g("copyFileFromHostToGuest", local_wrap, wrapper), T)
        if rc != 0:
            print("copy-in failed:", out)
            return 3
        rc, out = run(g("runProgramInGuest", "/bin/bash", wrapper), T)
        if rc != 0:
            print("run warning:", out)
        dst = os.path.abspath(a.out)
        rc, out = run(g("copyFileFromGuestToHost", "/tmp/agent_out.txt", dst), T)
        if rc != 0:
            print("copy-out failed:", out)
            return 4
        with open(dst, encoding="utf-8", errors="replace") as f:
            sys.stdout.write(f.read())
        return 0

    if a.cmd == "shot":
        if a.os == "linux":
            script = ("#!/bin/bash\nexport DISPLAY=:0\n"
                      "export XAUTHORITY=/home/%s/.Xauthority\n"
                      "import -window root /tmp/agent_shot.png 2>/dev/null\n"
                      "exit 0\n" % a.gu)
            local = os.path.join(tempfile.gettempdir(), "agent_shot.sh")
            with open(local, "w", encoding="utf-8", newline="\n") as f:
                f.write(script)
            run(g("copyFileFromHostToGuest", local, "/tmp/agent_shot.sh"), T)
            run(g("runProgramInGuest", "/bin/bash", "/tmp/agent_shot.sh"), T)
            rc, out = run(g("copyFileFromGuestToHost", "/tmp/agent_shot.png", os.path.abspath(a.out)), T)
        else:
            ps = ("Add-Type -AssemblyName System.Drawing,System.Windows.Forms;"
                  "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
                  "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
                  "$g=[System.Drawing.Graphics]::FromImage($bmp);"
                  "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
                  "$bmp.Save('C:\\Windows\\Temp\\agent_shot.png');")
            run(g("runProgramInGuest",
                  "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
                  "-NoProfile", "-Command", ps), T)
            rc, out = run(g("copyFileFromGuestToHost",
                            "C:\\Windows\\Temp\\agent_shot.png", os.path.abspath(a.out)), T)
        if rc != 0:
            print("shot failed:", out)
            return 4
        print("saved", a.out)
        return 0

    if a.cmd == "put":
        rc, out = run(g("copyFileFromHostToGuest", os.path.abspath(a.local), a.remote), T)
        print(out or ("ok" if rc == 0 else "failed"))
        return 0 if rc == 0 else 4

    if a.cmd == "get":
        rc, out = run(g("copyFileFromGuestToHost", a.remote, os.path.abspath(a.local)), T)
        print(out or ("ok" if rc == 0 else "failed"))
        return 0 if rc == 0 else 4

    return 0


if __name__ == "__main__":
    sys.exit(main())
