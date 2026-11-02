#!/usr/bin/env python3
"""Build the nbdevlab homelab map.

Edit the data in the first half of this file and run `python3 build.py`. It writes

  homelab-map.html        the page as an artifact (no doctype; the artifact host wraps it)
  site/nbdevlab-homelab.html   the same page as a standalone document for nbdevlab.com
  poster-*.html           each diagram alone at its natural size, for PNG export

and `./render.sh` turns the posters into 2x PNGs.

First read live on 2026-09-29: both Proxmox hosts (pvesh, lscpu, lsblk, zpool),
the Cloudflare account (tunnels, Workers), `tailscale status`, the UPS dashboard
API and ups-guardian on byteme2. Re-read on 2026-10-12: the two running Proxmox
hosts, Slurm and the orchestrator on slerm-head, models.ini, the UPS dashboard
API and ups-guardian. Cloudflare and Tailscale were not re-read then, and byteme3
was powered off, so its facts are from its setup on 2026-10-10.

This is the PUBLIC version. It carries no addresses (internal or public), port
numbers, VM ids, software versions, tunnel or admin hostnames, alert thresholds
or auth details, and nothing work-related. leak_check() refuses to write output
that matches any of those patterns. The pre-scrub build with IPs is kept in
private-2026-09-29/.
"""
import html
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
SNAPSHOT = "12 Oct 2026"
EDGE_READ = "29 Sep"  # Cloudflare and Tailscale were last read then

# --------------------------------------------------------------------- data --

NETS = {  # name, what lives there (no subnets on the public page)
    "lan": ("LAN · Wi-Fi", "the house"),
    "mgmt": ("mgmt", "hypervisors"),
    "srv": ("srv", "servers"),
    "dmz": ("DMZ", "isolated"),
}

# (kind, name, role, net, badges, state, ram GB, disk GB)
# state: run | demand (stopped until slerm needs it)
BYTEME2_GUESTS = [
    ("CT", "Technitium", "DNS · DHCP for Wi-Fi", "srv", [], "run", 6.1, 24),
    ("VM", "CFT", "tailnet router · CF tunnel", "srv", ["cf", "ts"], "run", 4.5, 15),
    ("CT", "PMG", "mail gateway → Brevo", "mgmt", [], "run", 6.0, 20),
    ("VM", "Wuzah", "Wazuh SIEM", "srv", ["wg", "ts"], "run", 10.8, 127),
    ("CT", "psql", "PostgreSQL", "srv", [], "run", 5.1, 32),
    ("VM", "HA", "Home Assistant OS", "srv", ["ts"], "run", 4.0, 32),
    ("CT", "nextcloud", "Nextcloud · 1.4 TB", "srv", [], "run", 8.1, 1400),
    ("VM", "Jellyfin", "media server", "dmz", ["wg"], "run", 6.1, 1000),
    ("VM", "Cryo-Ai", "Open WebUI · Ollama", "srv", [], "run", 6.1, 800),
    ("CT", "MCP", "mcpo · SearXNG", "srv", [], "run", 12.3, 75),
    ("VM", "AI-Sandbox", "computer-use and coding agents", "srv", [], "run", 8.0, 100),
    ("VM", "slerm-node01", "CPU worker · 16c 12 GB", "srv", ["slerm"], "demand", 12.0, 40),
    ("VM", "slerm-node02", "CPU worker · 16c 12 GB", "srv", ["slerm"], "demand", 12.0, 40),
]

BYTEME_GUESTS = [
    ("VM", "slerm-head", "Slurm · NFS · LLM gateway", "srv", ["slerm"], "run", 4.0, 40),
    ("VM", "slerm-node04", "2× Tesla P100 · LLM router", "srv", ["slerm"], "demand", 45.0, 40),
]

# Guests defined in Proxmox but stopped. Recounted on 12 Oct (byteme gained the retired copy of
# slerm-node03); the public page names products only, so personal, course and account names stay off it.
PARKED_COUNT = {"byteme2": 41, "byteme": 13}
PARKED_PUBLIC = [
    ("Firewalls", 4, "pfSense ×2, OPNsense, FortiGate"),
    ("Windows lab", 19, "Windows Server and Windows 11 VMs, a lab domain controller, clone templates and a gaming VM"),
    ("Security", 4, "REMnux ×2, OSINT, sentinel"),
    ("Services", 13, "OwnCloud, Zabbix, Gitea, WordPress, Drupal, Plex, Pi-hole, a second DNS server, Grafana, "
                     "Proxmox Datacenter Manager, a Proxmox dashboard, a homepage, 5eTools"),
    ("Projects and other", 14, "Ubuntu, Archangel, BlackPearl, Golem, Hivello, a five-VM Syslo lab with its client, "
                               "the retired copy of slerm-node03, two more"),
]
assert sum(n for _, n, _ in PARKED_PUBLIC) == sum(PARKED_COUNT.values())

WIFI = [  # the Wi-Fi scope: Technitium hands out the leases, the Linksys only radiates
    ("Linksys router", "AP mode only · Wi-Fi for the house"),
    ("Mesh extender", "one node, meshed to the Linksys"),
]

LAN_DEVICES = [
    ("Raspberry Pi 3B", "wall kiosk · status API for the site"),
    ("Ghost", "Arch laptop · syncs to Nextcloud"),
    ("Cyclops", "Windows · LM Studio embeddings"),
    ("Cube Pro", "3D printer · Klipper"),
    ("Tempest", "weather station → WeatherFlow"),
    ("ESP8266 fob", "OLED status fob ← byteme2"),
]

POWER = {  # watts read from the UPS dashboard API at snapshot time: the lab idle, every slerm node off
    "ups_w": 108, "ups_pct": 12, "runtime_min": 64,
    "byteme2": [("PSU1", "batt", 5), ("PSU2", "surge", 150)],
    "byteme": [("PSU1", "surge", 168), ("PSU2", "batt", 24)],
    "deadlock": [("PSU1", "surge", 6), ("PSU2", "batt", 0)],
}
BYTEME_LOADED_W = 574  # byteme at the wall with a model on both P100s, measured 4 Oct
GUARDIAN_BUDGET_MIN = 7  # the battery time ups-guardian is sized for, from its own header
POWER_CAP_W = 107  # the tightest cap byteme2's iLO accepts, measured 1 Oct
PROTECTED = {"Technitium", "CFT"}  # ups-guardian keeps these two up until low battery
SURGE_W = sum(w for host in ("byteme2", "byteme", "deadlock") for _, kind, w in POWER[host] if kind == "surge")

HARDWARE = [
    # machine, role, platform, cpu, memory, storage, network, power
    ("byteme2", "Proxmox VE · main hypervisor", "HP ProLiant DL360 Gen9",
     "2× Xeon E5-2683 v4 · 32C/64T", "64 GB",
     "ZFS raidz1 5× 1.2 TB SAS · 2× 1 TB SSD (LVM) · 128 GB boot SSD · 500 GB HDD",
     "4× 1 GbE · ConnectX-3 Pro 10 GbE (unused) · iLO",
     f"2 PSUs · {sum(w for _, _, w in POWER['byteme2'])} W now"),
    ("byteme", "Proxmox VE · slerm GPU host", "Dell PowerEdge R730",
     "2× Xeon E5-2695 v4 · 36C/72T", "64 GB",
     "ZFS raidz1 6× 1.2 TB SAS · btrfs RAID1 boot on 2× 1.2 TB SAS",
     "2× 10 GbE + 2× 1 GbE · iDRAC",
     f"2× 1100 W · {sum(w for _, _, w in POWER['byteme'])} W idle now · {BYTEME_LOADED_W} W with both GPUs loaded"),
    ("", "GPUs (passthrough)", "2× Tesla P100 16 GB (Pascal), both in slerm-node04",
     "", "32 GB VRAM", "", "", "passive cards, cooled by the chassis fans"),
    ("byteme3", "Proxmox VE · parked", "HP ProLiant DL380 Gen9",
     "2× Xeon E5-2690 v3 · 24C/48T", "none fitted",
     "ZFS raidz2 6× 1.2 TB SAS", "12× 1 GbE · 2× 10 GbE SFP+ · iLO",
     "2× 800 W · off since its memory went into byteme"),
    ("deadlock", "bare metal · slerm-node05", "Intel S1600JP board",
     "Xeon E5-1620 v2 · 4C/8T", "32 GB", "2.6 TB local (unused)", "1 GbE · BMC",
     "2 PSUs · off at idle, 6 W standby"),
    ("Starlink", "internet", "Starlink dish + router in front of the Firebox",
     "", "", "", "double NAT in front of the Firebox", "stays up after byteme2 halts"),
    ("Linksys", "Wi-Fi access point", "Linksys router in AP-only mode + 1 mesh extender",
     "", "", "", "uplink to the Firebox · DHCP from Technitium", ""),
    ("Firebox", "edge firewall and router", "WatchGuard Firebox M400",
     "", "", "", "8× 1 GbE · VLAN trunk to byteme2", ""),
    ("UPS", "battery for one PSU per server", "CyberPower LX1500GAVR",
     "", "", "", "USB → byteme2", f"1500 VA / 900 W · {POWER['ups_w']} W now"),
    ("Pi", "lab wall + public status API", "Raspberry Pi 3 Model B · Debian · Acer KA272 27″",
     "4× Cortex-A53", "1 GB", "microSD", "LAN", ""),
    ("VPS", "Oracle Cloud", "Ampere A1 (Neoverse-N1) · Ubuntu",
     "4 cores", "24 GB", "45 GB", "public IP · WireGuard hub", ""),
    ("Ghost", "daily driver", "HP ENVY x360 15 · Arch Linux · KDE Plasma 6",
     "Ryzen 5 4500U · 6C", "", "", "Wi-Fi · Tailscale", ""),
]

SLERM_NODES = [
    # name, where, cpu/ram, device, job, partitions, state (run | demand | parked). The router node comes first.
    ("slerm-node04", "VM · BYTEME", "36 vCPU · 45 GB", "2× Tesla P100 · 16 GB each", "llama-server router", ("gpu", "llm"), "demand"),
    ("slerm-node01", "VM · BYTEME2", "16 vCPU · 12 GB", "CPU only", "ggml-rpc worker", ("compute", "llmcpu"), "demand"),
    ("slerm-node02", "VM · BYTEME2", "16 vCPU · 12 GB", "CPU only", "ggml-rpc worker", ("compute", "llmcpu"), "demand"),
    ("slerm-node05", "BARE METAL · DEADLOCK", "8 threads · 32 GB", "CPU only", "ggml-rpc worker", ("compute", "llmcpu"), "demand"),
    ("slerm-node03", "VM · BYTEME3", "24 vCPU · 20 GB", "CPU only", "Slurm compute", ("compute",), "parked"),
]

TOK_S = [  # generation speed measured through the gateway on the two P100s (the last two spill onto node04's CPUs)
    ("ornith-1.5 35B-A3B", 46), ("gpt-oss 20B", 45), ("qwen3.6 35B-A3B", 45), ("gemma4 26B-A4B", 24),
    ("Coder-Next 80B-A3B", 11), ("gpt-oss 120B", 10),
]

SECURITY = [  # design rules, stated without addresses, ports or thresholds
    ("No inbound ports at home",
     "Starlink's NAT sits in front of the Firebox. Everything that comes in rides a connection the lab opened "
     "itself: a Cloudflare tunnel, WireGuard to the VPS, or Tailscale."),
    ("The public box can't see the lab",
     "The VPS is kept off the tailnet on purpose. Its WireGuard peers are locked down: one reaches only the "
     "Jellyfin VM, the other carries Wazuh agent traffic and nothing else."),
    ("Media sits in a DMZ",
     "Jellyfin has its own VLAN, and the Firebox keeps it apart from every other segment."),
    ("Admin pages need a login first",
     "Admin UIs on the web sit behind Cloudflare Access. Everything else is reachable only over the tailnet."),
    ("One SIEM sees everything",
     "The hypervisors, servers and the VPS report to Wazuh. It blocks SSH brute force on its own and mails "
     "serious alerts out through PMG."),
    ("This page leaves things out",
     "No addresses, port numbers, software versions or admin hostnames. The diagrams show how the lab is put "
     "together, not where to knock."),
]

CHANGES = [  # (date, what) — newest first
    ("11 Oct", "gpt-oss 120B and Coder-Next get a 128k context."),
    ("10 Oct", "byteme gets two 18-core Xeons and 64 GB. node04 grows to 36 vCPU and 45 GB, and the biggest models "
               "now keep their overflow on its own CPUs, so the CPU nodes stay asleep. A third Proxmox host, "
               "byteme3, is set up and then parked when its memory goes into byteme."),
    ("5 Oct", "Open WebUI gets a Code mode: a coding agent that works on the AI-Sandbox VM."),
    ("4 Oct", "Two Tesla P100s replace both slerm GPUs, both in node04: 32 GB of VRAM, and models run at 2.8 to "
              "4.6 times the speed of the old pool."),
    ("1 Oct", "Two planned pulls of the UPS plug. ups-guardian gets a round of fixes from them, and slerm now "
              "freezes its jobs the moment the UPS goes on battery."),
    ("29 Sep", "Model staging copies a model to every node it will load on before it is needed. "
               "Two 9B models join the pool at about 25 tok/s."),
    ("28 Sep", "The Pi lab wall goes up, and Open WebUI gets a computer-use agent that drives the AI-Sandbox desktop."),
    ("27 Sep", "slerm goes dynamic: a gateway that holds requests while nodes wake, and an orchestrator that powers "
               "them off when idle. The power dashboard gets an outage console and an energy tracker."),
    ("21 Sep", "The ESP8266 status fob."),
    ("19 Sep", "Rack recabled. The same day a 48 s blackout ran the whole power-failure sequence for real."),
    ("9 Sep", "deadlock joins slerm as node05, a bare-metal 32 GB RAM node."),
]

# Anything matching these must never reach the public page. Checked on every build.
LEAK_PATTERNS = [
    (r"\b10\.\d{1,3}\.\d{1,3}", "private address"),
    (r"\b192\.168\.\d", "private address"),
    (r"\b172\.(1[6-9]|2\d|3[01])\.\d", "private address"),
    (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "IPv4 address"),
    (r"\b\d{1,3}(\.\d{1,3}){1,3}/\d{1,2}\b", "subnet"),
    (r"(?<![\w.])\.\d{1,3} (Jellyfin|Wazuh)", "host part of an address"),
    (r"(?<![\w/]):\d{2,5}\b", "port number"),
    (r"\b(tcp|udp) ?\d{2,5}\b", "port number"),
    (r"\b(VM|CT) \d{3}\b", "VM id"),
    (r"\bVLAN \d+", "VLAN id"),
    (r"\b(eth|eno|nic)\d\b|\bbr\d\d_\w+|\bvmbr\d", "interface name"),
    (r"Fireware|Wazuh \d|Nextcloud \d|PostgreSQL \d|Slurm \d|Rocky \d|Ubuntu \d|Debian \d|VE \d|iLO \d|iDRAC\d",
     "software or firmware version"),
    (r"\bapi\.nbdevlab|jellyfin\.nbdevlab|\.home\.arpa|\bnic1\b", "hostname"),
    (r"allowlist|OTP\b|level ?\d+|≥ level", "auth or alert detail"),
    (r"/usr/|/etc/|/var/|/root/", "file path"),
]

# ------------------------------------------------------------ svg helpers --


def esc(s):
    return html.escape(str(s), quote=True)


def tw(s, size=12.5, mono=False, bold=False):
    """Rough text width in px; mono is exact at 0.6em."""
    if mono:
        return len(s) * size * 0.6
    return len(s) * size * (0.585 if bold else 0.55)


class Svg:
    def __init__(self, w, h, sid, label):
        self.w, self.h, self.sid, self.label = w, h, sid, label
        self.o = []
        self.pk = []  # animated packets, drawn last so they ride on top of the wires
        self.ndots = 0

    def t(self, x, y, s, c="", a="start", rot=None):
        cls = f' class="{c}"' if c else ""
        anc = f' text-anchor="{a}"' if a != "start" else ""
        tr = f' transform="rotate({rot} {x:g} {y:g})"' if rot is not None else ""
        if isinstance(s, list):  # [(text, class), ...] as tspans
            body = "".join(f'<tspan class="{k}">{esc(v)}</tspan>' if k else esc(v) for v, k in s)
        else:
            body = esc(s)
        self.o.append(f'<text x="{x:g}" y="{y:g}"{cls}{anc}{tr}>{body}</text>')

    def rect(self, x, y, w, h, c, rx=0):
        self.o.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx:g}" class="{c}"/>')

    def line(self, x1, y1, x2, y2, c, marker=False):
        m = f' marker-end="url(#ah-{self.sid})"' if marker else ""
        self.o.append(f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" class="{c}"{m}/>')

    def path(self, d, c, marker=False):
        m = f' marker-end="url(#ah-{self.sid})"' if marker else ""
        self.o.append(f'<path d="{d}" class="{c}"{m}/>')

    def circle(self, cx, cy, r, c):
        self.o.append(f'<circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" class="{c}"/>')

    def vwire(self, x, y1, y2, c, halo=None):
        """Vertical wire; halo=(ya, yb) masks crossings with a background-colored stroke."""
        if halo:
            self.line(x, halo[0], x, halo[1], "halo")
        self.line(x, y1, x, y2, c)

    def hr(self, x1, x2, y):
        self.line(x1, y, x2, y, "hr")

    def card(self, x, y, w, h, c="card"):
        self.rect(x, y, w, h, c, rx=10)

    def dot(self, x, y, state):
        if state != "run":
            self.circle(x, y, 3.5, "st-off")
            return
        # running dots breathe out of step with each other (only while the page has motion on)
        self.ndots += 1
        delay = -((self.ndots * 1.37) % 3.6)
        self.o.append(f'<circle cx="{x:g}" cy="{y:g}" r="3.5" class="st-run" style="animation-delay:{delay:.2f}s"/>')

    def packet(self, legs, colors, speed=120, delay=0, rest=1.5, hold=0.15):
        """A dot that travels the wires: legs are polylines [(x, y), ...]; between legs it is hidden
        (crossing a box) for as long as the jump would take at the same speed, plus `hold` seconds.
        colors names a token per leg (text, lan, mgmt, srv, dmz, violet, power). Seconds throughout."""
        if isinstance(colors, str):
            colors = [colors] * len(legs)
        d = ";".join(" ".join(f"{x:g},{y:g}" for x, y in leg) for leg in legs)
        self.pk.append(f'<g class="pk" data-legs="{d}" data-c="{" ".join(colors)}" data-speed="{speed:g}" '
                       f'data-delay="{delay:g}" data-rest="{rest:g}" data-hold="{hold:g}">'
                       f'<circle r="7" class="pk-h"/><circle r="2.6" class="pk-c"/></g>')

    def pill(self, x_right, y, text, kind="tun"):
        """Right-aligned pill ending at x_right with its text baseline at y; returns its left edge."""
        w = len(text) * 6 + 12
        self.rect(x_right - w, y - 11, w, 15, f"pill p-{kind}", rx=7.5)
        self.t(x_right - w / 2, y, text, f"m xs pt-{kind}", "middle")
        return x_right - w

    def render(self, extra_class=""):
        return (
            f'<svg class="pz {extra_class}" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
            f'role="img" aria-label="{esc(self.label)}" data-w="{self.w}">'
            f'<defs><marker id="ah-{self.sid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ah"/></marker></defs>'
            + "".join(self.o) + "".join(self.pk) + "</svg>"
        )


def badges(S, x_right, y, names):
    x = x_right
    for b in reversed(names):
        x = S.pill(x, y, b, "slerm" if b == "slerm" else "tun") - 5
    return x


def title_block(S, y, word, rest, sub):
    S.t(60, y, [(word, ""), (rest, "mu")], "big")
    S.t(60, y + 28, sub, "sm mu")


def band_label(S, text, y):
    S.t(30, y, text.upper(), "ey", "middle", rot=-90)


# ---------------------------------------------------- poster 1: the network --


def poster_network():
    W = 1680
    S = Svg(W, 1560, "net", "Homelab topology: internet services, the Firebox, four networks, three servers "
            "with their running guests, a parked fourth server, LAN devices and UPS power wiring.")

    title_block(S, 62, "nbdevlab", " homelab",
                f"Two Proxmox hosts and a third parked · a bare-metal RAM node · the slerm Slurm cluster · Cloudflare edge · "
                f"snapshot {SNAPSHOT}")

    # legend
    lx = 1040
    for i, (key, (name, net)) in enumerate(NETS.items()):
        y = 40 + i * 20
        S.line(lx, y - 4, lx + 24, y - 4, f"w s-{key}")
        S.t(lx + 34, y, name, f"sm f-{key}")
        S.t(lx + 134, y, net, "m xs mu")
    lx2 = 1330
    S.dot(lx2 + 4, 36, "run")
    S.t(lx2 + 14, 40, "running", "sm")
    S.dot(lx2 + 84, 36, "demand")
    S.t(lx2 + 94, 40, "off until needed", "sm")
    S.pill(lx2 + 44, 60, "slerm", "slerm")
    S.t(lx2 + 52, 60, "slerm cluster node", "sm")
    x = badges(S, lx2 + 88, 80, ["cf", "wg", "ts"])
    S.t(lx2 + 96, 80, "outbound tunnel from here", "sm")
    S.line(lx2, 96, lx2 + 24, 96, "pw-b")
    S.t(lx2 + 32, 100, "battery outlet", "sm")
    S.line(lx2 + 132, 96, lx2 + 156, 96, "pw-s")
    S.t(lx2 + 164, 100, "surge only", "sm")

    # ---- internet band
    band_label(S, "internet", 214)
    cards = [
        ("CLOUDFLARE · PRO ZONE", "nbdevlab.com", [
            "DNS · WAF · Zero Trust Access for admin UIs",
            "Worker nbdevlab serves the website",
            "   D1 content · R2 images · GA4 after consent",
            "Tunnel from byteme2 · cloudflared on the host",
            "Tunnel from the server network · on CFT",
        ], "2 tunnels", True),
        ("ORACLE CLOUD VPS · AMPERE A1", "public relay", [
            "4 Arm cores · 24 GB · Ubuntu",
            "Caddy + Let's Encrypt in front of Jellyfin",
            "WireGuard hub with two locked-down peers",
            "   Jellyfin · Wazuh agent traffic only",
            "fail2ban · watched by Wazuh",
        ], "WireGuard ×2", True),
        ("TAILSCALE", "tailnet", [
            "byteme2 · subnet router + exit node",
            "CFT · routes the Wi-Fi and server networks",
            "Home Assistant · exit node",
            "tailnet DNS → Technitium",
            "also Wuzah · Ghost · Cyclops · phone",
        ], "4 lab nodes", True),
        ("UPSTREAM", "what the lab calls out to", [
            "WeatherFlow ← Tempest readings",
            "Brevo ← outbound mail relay from PMG",
            "GitHub ← code for the Pi wall",
            "Hugging Face ← slerm model downloads",
            "Let's Encrypt ← certificates for the VPS",
        ], "HTTPS", False),
    ]
    cy, ch, cw, gap = 132, 164, 372, 24
    rail = 328
    centers = []
    for i, (ey, ti, rows, drop, dashed) in enumerate(cards):
        x0 = 60 + i * (cw + gap)
        S.card(x0, cy, cw, ch)
        S.t(x0 + 16, cy + 24, ey, "ey")
        S.t(x0 + 16, cy + 48, ti, "ti")
        for j, r in enumerate(rows):
            S.t(x0 + 16, cy + 74 + j * 19, r, "sm")
        c = x0 + cw / 2
        centers.append(c)
        S.line(c, cy + ch, c, rail, "nt dash" if dashed else "nt")
        S.t(c + 8, cy + ch + 20, drop, "m xs mu")
    S.line(centers[0], rail, centers[-1], rail, "nt")

    # ---- edge
    band_label(S, "edge", 450)
    fx, fy, fw, fh = 520, 404, 640, 90
    pill_w = 170
    S.line(840, rail, 840, 346, "nt")
    S.rect(840 - pill_w / 2, 346, pill_w, 24, "pill p-tun", rx=12)
    S.t(840, 362, "Starlink · double NAT", "m sm", "middle")
    S.line(840, 370, 840, fy, "nt")
    S.card(fx, fy, fw, fh, "card card-hi")
    S.t(fx + 16, fy + 24, "EDGE FIREWALL · ROUTER · GATEWAY FOR EVERY SEGMENT", "ey")
    S.t(fx + 16, fy + 50, "WatchGuard Firebox M400", "ti")
    S.t(fx + 16, fy + 72, "Policies between every segment · the DMZ is its own zone · VLAN trunk to byteme2", "m xs mu")

    # ---- networks: four buses
    band_label(S, "networks", 587)
    bus_y = {"lan": 548, "mgmt": 574, "srv": 600, "dmz": 626}
    bus_x0 = 236
    fw_ports = {"lan": 600, "mgmt": 720, "srv": 840, "dmz": 960}

    # host cards and their ports decide bus extents
    top = 690
    hosts = {
        "byteme2": dict(x=60, w=560, ports=[(280, "lan", "LAN"), (350, "mgmt", "mgmt"), (420, "srv", "srv"),
                                            (490, "dmz", "DMZ"), (560, "srv", "iLO")]),
        "byteme": dict(x=644, w=440, ports=[(784, "mgmt", "mgmt + iDRAC"), (874, "srv", "srv")]),
        "deadlock": dict(x=1108, w=236, ports=[(1226, "srv", "srv + BMC")]),
        "lan": dict(x=1368, w=252, ports=[(1494, "lan", "Wi-Fi AP")]),
    }
    ext = {k: max([fw_ports[k]] + [p[0] for h in hosts.values() for p in h["ports"] if p[1] == k]) for k in NETS}
    for k, (name, desc) in NETS.items():
        y = bus_y[k]
        S.t(60, y + 4, [(name, f"f-{k}"), ("  " + desc, "m xs mu")], "sm")
        S.line(bus_x0, y, ext[k] + 14, y, f"w s-{k}")
    for k, px in fw_ports.items():
        y = bus_y[k]
        S.vwire(px, fy + fh, y, f"w s-{k}", halo=(fy + fh, y - 6) if y > bus_y["lan"] else None)
        S.circle(px, y, 3, f"f-{k}")
        S.rect(px - 4, fy + fh - 4, 8, 8, f"f-{k}", rx=2)
    for h in hosts.values():
        for px, k, label in h["ports"]:
            y = bus_y[k]
            S.vwire(px, y, top, f"w s-{k}", halo=(y + 6, top))
            S.circle(px, y, 3, f"f-{k}")
            S.rect(px - 4, top - 4, 8, 8, f"f-{k}", rx=2)
            S.t(px, top + 26, label, "m xs mu", "middle")

    # ---- hosts
    band_label(S, "hosts", 1000)
    bottoms = {}

    def host_head(h, eyebrow, name, specs):
        x0, w = h["x"], h["w"]
        S.hr(x0 + 1, x0 + w - 1, top + 48)
        S.t(x0 + 16, top + 70, eyebrow, "ey")
        S.t(x0 + 16, top + 94, name, "ti")
        for i, s in enumerate(specs):
            S.t(x0 + 16, top + 114 + i * 17, s, "m xs")
        S.hr(x0 + 1, x0 + w - 1, top + 146)

    def guest_line(x0, w, y, g, twoline=False):
        kind, name, role, net, bdg, state = g[:6]
        S.dot(x0 + 20, y - 4, state)
        S.t(x0 + 32, y, name, "nm")
        S.line(x0 + w - 28, y - 4, x0 + w - 16, y - 4, f"stub s-{net}")
        badges(S, x0 + w - 38, y, bdg)
        if twoline:
            S.t(x0 + 32, y + 17, f"{kind} · {role}", "sm mu")
        else:
            S.t(x0 + 136, y, kind, "m xs mu")
            S.t(x0 + 164, y, role, "sm")

    def psu_strip(hname, h, y_hr, xs):
        x0, w = h["x"], h["w"]
        S.hr(x0 + 1, x0 + w - 1, y_hr)
        ports = []
        for (label, kind, watts), px in zip(POWER[hname], xs):
            S.t(px, y_hr + 22, f"{label} · {watts} W", "m xs tx", "middle")
            ports.append((px, kind, watts))
        bottom = y_hr + 36
        for px, kind, _ in ports:
            S.rect(px - 4, bottom - 4, 8, 8, "psu", rx=2)
        return bottom, ports

    # byteme2
    h = hosts["byteme2"]
    x0, w = h["x"], h["w"]
    host_head(h, "PROXMOX VE · HP PROLIANT DL360 GEN9", "byteme2",
              ["2× Xeon E5-2683 v4 · 32C/64T · 64 GB RAM",
               "ZFS raidz1 5× 1.2 TB SAS · 2× 1 TB SSD · 4× 1 GbE"])
    y = top + 172
    for g in BYTEME2_GUESTS:
        guest_line(x0, w, y, g)
        y += 26
    S.hr(x0 + 1, x0 + w - 1, y - 6)
    S.t(x0 + 16, y + 16, f"+{PARKED_COUNT['byteme2']} more guests defined but stopped", "sm mu")
    S.t(x0 + 16, y + 40, "On the host: cloudflared · Tailscale subnet router + exit node", "sm")
    S.t(x0 + 16, y + 58, "UPS dashboard · ups-guardian · fob API · Wazuh agent", "sm")
    b, p1 = psu_strip("byteme2", h, y + 76, [x0 + 140, x0 + 420])
    bottoms["byteme2"] = (b, p1)
    S.card(x0, top, w, b - top, "card frame")

    # byteme
    h = hosts["byteme"]
    x0, w = h["x"], h["w"]
    host_head(h, "PROXMOX VE · DELL POWEREDGE R730", "byteme",
              ["2× Xeon E5-2695 v4 · 36C/72T · 64 GB RAM",
               "ZFS raidz1 6× 1.2 TB SAS · btrfs RAID1 boot"])
    y = top + 172
    for g in BYTEME_GUESTS:
        guest_line(x0, w, y, g, twoline=True)
        y += 44
    S.hr(x0 + 1, x0 + w - 1, y - 14)
    S.t(x0 + 16, y + 8, "PCIE PASSTHROUGH", "ey")
    S.t(x0 + 16, y + 30, "82:00  Tesla P100 · 16 GB · Pascal  → node04", "m xs")
    S.t(x0 + 16, y + 48, "04:00  Tesla P100 · 16 GB · Pascal  → node04", "m xs")
    S.t(x0 + 16, y + 70, "Both cards since 4 Oct · 32 GB of VRAM in one VM", "sm mu")
    S.hr(x0 + 1, x0 + w - 1, y + 86)
    S.t(x0 + 16, y + 108, "The cards are passive, so the chassis fans cool", "sm")
    S.t(x0 + 16, y + 126, "them. The iDRAC ramps the fans on its own.", "sm")
    S.t(x0 + 16, y + 150, f"+{PARKED_COUNT['byteme']} more guests defined but stopped", "sm mu")
    b, p2 = psu_strip("byteme", h, y + 168, [x0 + 110, x0 + 330])
    bottoms["byteme"] = (b, p2)
    S.card(x0, top, w, b - top, "card frame")

    # deadlock
    h = hosts["deadlock"]
    x0, w = h["x"], h["w"]
    host_head(h, "BARE METAL · INTEL S1600JP", "deadlock",
              ["Xeon E5-1620 v2 · 4C/8T", "32 GB RAM · 2.6 TB local"])
    y = top + 172
    S.dot(x0 + 20, y - 4, "demand")
    S.t(x0 + 32, y, "slerm-node05", "nm")
    S.pill(x0 + w - 16, y, "slerm", "slerm")
    S.t(x0 + 32, y + 18, "CPU worker · the RAM node", "sm mu")
    S.t(x0 + 32, y + 36, "powers off when idle, the", "sm mu")
    S.t(x0 + 32, y + 54, "BMC wakes it on demand", "sm mu")
    b, p3 = psu_strip("deadlock", h, y + 72, [x0 + 60, x0 + 176])
    bottoms["deadlock"] = (b, p3)
    S.card(x0, top, w, b - top, "card frame")

    # LAN devices
    h = hosts["lan"]
    x0, w = h["x"], h["w"]
    S.hr(x0 + 1, x0 + w - 1, top + 48)
    S.t(x0 + 16, top + 70, "THE HOUSE · DHCP FROM TECHNITIUM", "ey")
    S.t(x0 + 16, top + 94, "Wi-Fi + LAN", "ti")
    S.hr(x0 + 1, x0 + w - 1, top + 110)
    y = top + 136
    for name, detail in WIFI:
        S.t(x0 + 16, y, name, "nm")
        S.t(x0 + 16, y + 17, detail, "sm mu")
        y += 42
    S.hr(x0 + 1, x0 + w - 1, y - 14)
    y += 10
    for name, detail in LAN_DEVICES:
        S.t(x0 + 16, y, name, "nm")
        S.t(x0 + 16, y + 17, detail, "sm mu")
        y += 42
    S.card(x0, top, w, y - 14 - top, "card frame")

    # byteme3: set up on 10 Oct, then parked. No wires: it is powered off and not on the UPS rails here.
    py0 = y - 14 + 20
    S.t(x0 + 16, py0 + 24, "PARKED · HP PROLIANT DL380 GEN9", "ey")
    S.t(x0 + 16, py0 + 48, "byteme3", "ti")
    S.t(x0 + 16, py0 + 70, "2× Xeon E5-2690 v3 · 24C/48T", "m xs")
    S.t(x0 + 16, py0 + 87, "ZFS raidz2 6× 1.2 TB SAS", "m xs")
    S.t(x0 + 16, py0 + 109, "Third Proxmox host, off for now:", "sm mu")
    S.t(x0 + 16, py0 + 126, "its memory went into byteme.", "sm mu")
    S.t(x0 + 16, py0 + 143, "Holds slerm-node03.", "sm mu")
    S.card(x0, py0, w, 158, "card frame parked-card")

    # ---- power
    B = max(v[0] for v in bottoms.values())
    rail_b, rail_s = B + 44, B + 66
    ups_x, ups_y, ups_w, ups_h = 500, B + 112, 500, 92
    out_b, out_s = 640, 860
    band_label(S, "power", B + 110)
    batt = [px for _, (b, ports) in bottoms.items() for px, k, _ in ports if k == "batt"]
    surge = [px for _, (b, ports) in bottoms.items() for px, k, _ in ports if k == "surge"]
    S.line(min(batt + [out_b]), rail_b, max(batt + [out_b]), rail_b, "pw-b")
    S.line(min(surge + [out_s]), rail_s, max(surge + [out_s]), rail_s, "pw-s")
    for hname, (b, ports) in bottoms.items():
        for px, k, _ in ports:
            if k == "batt":
                S.vwire(px, b + 4, rail_b, "pw-b")
            else:
                S.vwire(px, b + 4, rail_s, "pw-s", halo=(b + 6, rail_s - 6))
    S.vwire(out_b, rail_b, ups_y, "pw-b", halo=(rail_b + 6, ups_y))
    S.vwire(out_s, rail_s, ups_y, "pw-s")
    S.t(out_b + 8, ups_y - 12, "battery outlets", "xs mu")
    S.t(out_s + 8, ups_y - 12, "surge-only outlets", "xs mu")
    S.card(ups_x, ups_y, ups_w, ups_h, "card card-hi")
    S.t(ups_x + 16, ups_y + 24, "UPS · USB TO BYTEME2", "ey")
    S.t(ups_x + 16, ups_y + 50, "CyberPower LX1500GAVR", "ti")
    S.t(ups_x + 16, ups_y + 74,
        f"1500 VA / 900 W · {POWER['ups_w']} W now ({POWER['ups_pct']}%) · ~{POWER['runtime_min']} min at this load",
        "m xs")
    S.line(360, ups_y + 46, ups_x - 2, ups_y + 46, "nt", marker=True)
    S.t(360, ups_y + 38, "mains 120 V", "m xs mu")
    notes = [
        "One PSU of each server sits on battery, the other on surge-only.",
        "On battery, ups-guardian on byteme2 shuts its guests down and",
        "powers byteme off through the iDRAC and deadlock through its BMC.",
        f"DNS and the tailnet router stay up; byteme2 caps itself at {POWER_CAP_W} W.",
        "Starlink stays up after byteme2 halts, so Wi-Fi lasts a while longer.",
        "When mains return, everything that was running comes back.",
    ]
    for i, n in enumerate(notes):
        S.t(1040, ups_y + 4 + i * 19, n, "sm")
    S.t(1040, ups_y + 4 + len(notes) * 19 + 6,
        f"Total draw now ≈ {POWER['ups_w'] + SURGE_W} W: {POWER['ups_w']} W through the UPS + {SURGE_W} W on surge-only.",
        "sm mu")

    # ---- traffic: example paths along the real wires (animated in the page, invisible in PNGs)
    starlink_in = [(840, 370), (840, fy)]

    def inbound(i, net, host_px, delay, rest=4.0):
        c = centers[i]
        legs = [[(c, cy + ch), (c, rail), (840, rail), (840, 346)], starlink_in,
                [(fw_ports[net], fy + fh), (fw_ports[net], bus_y[net]), (host_px, bus_y[net]), (host_px, top)]]
        S.packet(legs, ["text", "text", net], delay=delay, rest=rest)

    inbound(0, "srv", 420, 0.0)     # a site visitor's status call, Cloudflare -> cloudflared on CFT
    inbound(1, "dmz", 490, 2.2)     # a stream, VPS -> Jellyfin in the DMZ
    inbound(2, "mgmt", 350, 4.6)    # tailnet admin -> byteme2
    lan = bus_y["lan"]
    S.packet([[(1494, top), (1494, lan), (fw_ports["lan"], lan), (fw_ports["lan"], fy + fh)],
              [(840, fy), (840, 370)], [(840, 346), (840, rail), (centers[3], rail), (centers[3], cy + ch)]],
             ["lan", "text", "text"], delay=6.4, rest=3.5)                      # Tempest -> WeatherFlow
    S.packet([[(1494, top), (1494, lan), (fw_ports["lan"], lan), (fw_ports["lan"], fy + fh)],
              [(fw_ports["srv"], fy + fh), (fw_ports["srv"], bus_y["srv"]), (420, bus_y["srv"]), (420, top)]],
             ["lan", "srv"], delay=1.3, rest=5.0)                               # Pi status API -> CFT
    S.packet([[(420, top), (420, bus_y["srv"]), (874, bus_y["srv"]), (874, top)]],
             "violet", delay=3.1, rest=2.5)                                     # Open WebUI -> slerm gateway
    S.packet([[(350, top), (350, bus_y["mgmt"]), (784, bus_y["mgmt"]), (784, top)]],
             "mgmt", delay=5.5, rest=7.0)                                       # ups-guardian -> iDRAC
    # power: mains into the UPS, then battery outlets up to every PSU that is drawing
    S.packet([[(360, ups_y + 46), (ups_x - 2, ups_y + 46)]], "power", speed=70, rest=0.6)
    k = 0
    for hname, (b, ports) in bottoms.items():
        for px, kind, watts in ports:
            if kind == "batt" and watts > 0:
                for j in range(2):
                    S.packet([[(out_b, ups_y), (out_b, rail_b), (px, rail_b), (px, b + 4)]], "power",
                             speed=70, delay=k * 1.1 + j * 3.3, rest=1.2)
                k += 1
    S.h = ups_y + 176
    return S


# ------------------------------------------------------ poster 2: slerm -----


SLERM_WORKLOADS = [
    # name, what it is for, (source title, lines), (job title, lines, partitions), (result title, lines)
    ("NOAA radar", "storms and wind, scan by scan",
     ("NOAA open data", ["NEXRAD Level II radar scans", "HRRR wind analysis"]),
     ("Array job, one task per scan", ["Py-ART decode + matplotlib, CPU only"], ("compute", "gpu")),
     ("Five products as GIF loops", ["reflectivity · rotation · storm cells", "wind profiles · US wind · the lab wall radar"])),
    ("Wazuh analysis", "security alerts against their own baseline",
     ("Wuzah, the home Wazuh manager", ["alert snapshot saved as JSONL", "or a CSV export dropped into the panel"]),
     ("Array of counter shards", ["then one dependent job reduces them"], ("compute",)),
     ("Report of detector findings", ["one baseline over the whole window", "AI triage on the LLM router"])),
    ("LLM serving", "local models behind one OpenAI-style endpoint",
     ("Open WebUI, opencode, agents", ["zsh-ai, Firstlook, Wazuh triage", "all through the gateway on the head"]),
     ("llama.cpp router job on node04", ["both P100s · CPU workers on demand"], ("gpu",)),
     ("Answers back through the gateway", ["nodes power off when nothing asks", "in detail in the next diagram"])),
    ("Builds", "software compiled on the nodes that run it",
     ("Source on the shared NFS", ["llama.cpp with the P100 patches", "desktop apps packaged as AppImages"]),
     ("Build and test jobs", ["CUDA builds and P100 tests need the cards"], ("compute", "gpu")),
     ("Binaries back on the NFS", ["router builds tuned for Pascal", "AppImages for the desktop"])),
]


def poster_workloads():
    W = 1680
    S = Svg(W, 760, "slerm-work", "slerm workloads: Slurm on slerm-head runs NOAA radar processing, Wazuh alert "
            "analysis, LLM serving and software builds as jobs on the compute and gpu partitions.")
    title_block(S, 62, "slerm", " workloads",
                "Slurm · five nodes on four machines · every workload is a Slurm job, submitted from the head")
    S.dot(1334, 36, "run")
    S.t(1344, 40, "running now", "sm")
    S.dot(1444, 36, "demand")
    S.t(1454, 40, "powered off until needed", "sm")

    # head
    hx, hy, hw = 60, 140, 380
    rows = [
        ("Slurm", "slurmctld + slurmdbd on MariaDB"),
        ("panel", "submits, schedules and watches jobs"),
        ("slerm-orch", "LLM gateway · powers nodes"),
        ("NFS · 700 GB", "data, apps and home directories"),
    ]
    S.t(hx + 16, hy + 24, "VM ON BYTEME · ROCKY LINUX · 2 vCPU · 4 GB", "ey")
    S.dot(hx + 20, hy + 46, "run")
    S.t(hx + 32, hy + 50, "slerm-head", "ti")
    S.hr(hx + 1, hx + hw - 1, hy + 68)
    for i, (n, d) in enumerate(rows):
        yy = hy + 96 + i * 44
        S.t(hx + 16, yy, n, "nm")
        S.t(hx + 128, yy, d, "sm")
        if i:
            S.hr(hx + 16, hx + hw - 16, yy - 26)
    hh = 96 + (len(rows) - 1) * 44 + 30
    S.card(hx, hy, hw, hh, "card frame")

    # partitions
    py = hy + hh + 44
    S.t(hx, py, "PARTITIONS", "ey")
    parts = [("compute", [n for n in SLERM_NODES if "compute" in n[5]]),
             ("gpu", [n for n in SLERM_NODES if "gpu" in n[5]])]
    y = py + 16
    for name, nodes in parts:
        h = 44 + len(nodes) * 22
        S.card(hx, y, hw, h, "card frame")
        S.t(hx + 16, y + 26, name, "nm")
        for i, n in enumerate(nodes):
            yy = y + 52 + i * 22
            S.dot(hx + 20, yy - 4, "parked" if n[6] == "parked" else n[6])
            S.t(hx + 32, yy, n[0].replace("slerm-", ""), "sm tx")
            where = n[1].replace("VM · ", "").replace("BARE METAL · ", "").lower()
            S.t(hx + 104, yy, f"{where} · {n[2]}" + (" · parked" if n[6] == "parked" else ""), "sm mu")
        y += h + 14

    # workload lanes: source -> Slurm job -> result
    x0, cw, gap = 520, 350, 34
    cols = [x0 + i * (cw + gap) for i in range(3)]
    for c, head in zip(cols, ["SOURCE", "SLURM JOB", "RESULT"]):
        S.t(c, hy + 4, head, "ey")
    ly, lane_h, ch = hy + 30, 136, 92
    bus_x = 486
    lane_mid = []
    for i, (name, what, src, job, res) in enumerate(SLERM_WORKLOADS):
        top = ly + i * lane_h
        S.t(x0, top + 14, [(name, ""), (f"  ·  {what}", "mu")], "nm")
        cy = top + 26
        mid = cy + ch / 2
        lane_mid.append(top + 10)
        for c, (title, lines, *rest) in zip(cols, (src, job, res)):
            S.card(c, cy, cw, ch, "card frame")
            S.t(c + 16, cy + 26, title, "nm")
            for k, line in enumerate(lines):
                S.t(c + 16, cy + 48 + k * 19, line, "sm" if k == 0 else "sm mu")
            if rest:
                px = c + 16
                for part in rest[0]:
                    w = len(part) * 6 + 12
                    S.rect(px, cy + 64, w, 15, "pill p-tun", rx=7.5)
                    S.t(px + w / 2, cy + 75, part, "m xs pt-tun", "middle")
                    px += w + 5
        for a, b in zip(cols, cols[1:]):
            S.line(a + cw + 4, mid, b - 6, mid, "nt", marker=True)
        S.packet([[(cols[0] + cw + 4, mid), (cols[1] - 6, mid)], [(cols[1] + cw + 4, mid), (cols[2] - 6, mid)]],
                 "violet", speed=90, delay=i * 1.9, rest=6, hold=0.5)

    # the head hands every workload to Slurm
    sy = hy + 96 - 4
    S.line(hx + hw, sy, bus_x, sy, "req")
    S.line(bus_x, sy, bus_x, lane_mid[-1], "req")
    for m in lane_mid:
        S.line(bus_x, m, x0 - 10, m, "req", marker=True)

    fy = ly + len(SLERM_WORKLOADS) * lane_h + 12
    S.t(60, fy, "Every workload is an ordinary Slurm job, so they share the nodes and Slurm keeps their CPU, memory and "
        "GPU requests apart. Radar arrays ask for no GPU, so the LLM router can still get both cards.", "sm")
    S.h = fy + 30
    return S


def poster_slerm():
    W = 1680
    S = Svg(W, 820, "slerm", "slerm cluster: clients call one gateway on slerm-head, which starts a llama.cpp router "
            "on node04; the router runs a model on its two Tesla P100s and keeps any overflow on node04's own CPUs.")
    title_block(S, 62, "slerm", " LLM serving",
                "one slerm workload · llama.cpp on two Tesla P100s, CPU overflow for the biggest models")
    S.dot(1334, 36, "run")
    S.t(1344, 40, "running now", "sm")
    S.dot(1444, 36, "demand")
    S.t(1454, 40, "powered off until a request", "sm")
    S.line(1334, 60, 1358, 60, "req")
    S.t(1366, 64, "request path", "sm")

    # clients
    clients = [
        ("Open WebUI", "chat, on Cryo-Ai"),
        ("opencode", "on Ghost and in Open WebUI Code mode"),
        ("Computer Agent", "drives the AI-Sandbox desktop"),
        ("delegate", "Claude Code hands off grunt work"),
        ("zsh-ai", "shell assistant"),
        ("Firstlook", "eBay listing filter"),
        ("Wazuh triage", "slerm panel, alerts from Wuzah"),
    ]
    S.t(60, 150, "CLIENTS · ONE OPENAI-STYLE ENDPOINT", "ey")
    y = 180
    ys = []
    for name, detail in clients:
        S.t(60, y, name, "nm")
        S.t(60, y + 16, detail, "sm mu")
        S.line(300, y - 4, 356, y - 4, "req")
        ys.append(y - 4)
        y += 40
    S.line(356, ys[0], 356, ys[-1], "req")

    # head
    hx, hy, hw = 400, 150, 400
    rows = [
        ("gateway", "holds requests while nodes wake"),
        ("slerm-orch", "starts routers · idles · powers nodes"),
        ("Slurm", "slurmctld + slurmdbd on MariaDB"),
        ("NFS · 700 GB", "models, apps and home directories"),
        ("panel", "cluster, jobs, AI usage, Wazuh triage"),
    ]
    S.t(hx + 16, hy + 24, "VM ON BYTEME · ROCKY LINUX · 2 vCPU · 4 GB", "ey")
    S.dot(hx + 20, hy + 46, "run")
    S.t(hx + 32, hy + 50, "slerm-head", "ti")
    S.hr(hx + 1, hx + hw - 1, hy + 68)
    gy = hy + 96
    for i, (n, d) in enumerate(rows):
        yy = hy + 96 + i * 44
        S.t(hx + 16, yy, n, "nm")
        S.t(hx + 128, yy, d, "sm")
        if i:
            S.hr(hx + 16, hx + hw - 16, yy - 26)
    hh = 96 + (len(rows) - 1) * 44 + 30
    S.card(hx, hy, hw, hh, "card frame")
    S.line(356, gy - 4, hx - 2, gy - 4, "req", marker=True)

    # node04 (router, both GPUs)
    nx, ny, nw, nh = 880, 150, 360, 170
    n04 = SLERM_NODES[0]
    S.card(nx, ny, nw, nh, "card card-hi")
    S.t(nx + 16, ny + 24, f"{n04[1]} · {n04[2]}", "ey")
    S.dot(nx + 20, ny + 46, n04[6])
    S.t(nx + 32, ny + 50, n04[0], "ti")
    S.t(nx + 16, ny + 76, "2× Tesla P100 · 16 GB each · Pascal (cc 6.0)", "sm")
    S.t(nx + 16, ny + 96, "llama-server in router mode, one model at a time", "sm")
    S.t(nx + 16, ny + 116, "100 GB local model cache · a 1B task model beside it", "sm")
    px = nx + 16
    for p in n04[5]:
        w = len(p) * 6 + 12
        S.rect(px, ny + 136, w, 15, "pill p-tun", rx=7.5)
        S.t(px + w / 2, ny + 147, p, "m xs pt-tun", "middle")
        px += w + 5
    S.line(hx + hw, gy - 4, nx - 2, gy - 4, "req", marker=True)
    S.t((hx + hw + nx) / 2, gy - 12, "HTTP", "m xs mu", "middle")

    # tensor split, to scale
    tx, tw_ = 1264, 356
    S.t(tx, 174, "HOW A MODEL IS SPLIT ACROSS THE POOL", "ey")
    # layers per device: qwen3.6 Q5 is split 47,53; gpt-oss 120B keeps 17 of its 37 layers on the cards (45,55)
    devs = [("P100 #1", "gpu1"), ("P100 #2", "gpu2"), ("node04 CPUs", "cpu3")]
    bars = [("qwen3.6 35B-A3B (25 GB): both cards", [47, 53, 0]),
            ("gpt-oss 120B (59 GB): overflow on the CPUs", [21, 25, 54])]
    by = 200
    for label, split in bars:
        S.t(tx, by, label, "sm")
        x = tx
        for (dname, cls), share in zip(devs, split):
            if not share:
                continue
            w = tw_ * share / 100
            S.rect(x, by + 8, w - 1.5, 16, f"seg {cls}", rx=2)
            if w > 70:
                S.t(x + 6, by + 20, f"{dname} {share}", "m xs seg-t")
            x += w
        by += 50
    kx = tx
    for dname, cls in devs:
        S.rect(kx, by - 10, 10, 10, f"seg {cls}", rx=2)
        S.t(kx + 14, by - 1, dname, "m xs mu")
        kx += 14 + len(dname) * 6.6 + 12
    S.t(tx, by + 22, "layer shares from models.ini · small models use one card", "xs mu")

    # workers
    wy, ww, wh, wgap = 410, 170, 150, 20
    dist_y = 372
    S.line(nx + nw / 2, ny + nh, nx + nw / 2, dist_y, "req")
    wx0 = 880
    centers = [wx0 + i * (ww + wgap) + ww / 2 for i in range(4)]
    rpc = [i for i, n in enumerate(SLERM_NODES[1:]) if "llmcpu" in n[5]]  # nodes the router can reach over rpc
    S.line(centers[rpc[0]], dist_y, centers[rpc[-1]], dist_y, "req")
    S.t(nx + nw / 2 + 10, dist_y - 10, "ggml-rpc · CPU nodes can join or stand in for node04 · no preset needs them now",
        "m xs mu")
    state_text = {"run": "running", "demand": "off until needed", "parked": "parked with byteme3"}
    for i, n in enumerate(SLERM_NODES[1:]):
        x0 = wx0 + i * (ww + wgap)
        if i in rpc:
            S.line(centers[i], dist_y, centers[i], wy - 2, "req", marker=True)
        S.card(x0, wy, ww, wh, "card frame parked-card" if n[6] == "parked" else "card frame")
        S.t(x0 + 14, wy + 22, n[1], "ey")
        S.dot(x0 + 18, wy + 42, n[6])
        S.t(x0 + 30, wy + 46, n[0], "nm")
        S.t(x0 + 14, wy + 70, n[3], "sm")
        S.t(x0 + 14, wy + 88, n[2], "sm mu")
        S.t(x0 + 14, wy + 106, state_text[n[6]], "m xs mu")
        px = x0 + 14
        for p in n[5]:
            w = len(p) * 6 + 12
            S.rect(px, wy + 120, w, 15, "pill p-tun", rx=7.5)
            S.t(px + w / 2, wy + 131, p, "m xs pt-tun", "middle")
            px += w + 5

    # measured speeds, to scale
    S.t(60, 486, "GENERATION SPEED ON THIS POOL (TOK/S)", "ey")
    mx = max(v for _, v in TOK_S)
    for i, (m, v) in enumerate(TOK_S):
        yy = 512 + i * 20
        S.t(60, yy, m, "sm")
        S.rect(196, yy - 9, 110 * v / mx, 10, "bar", rx=2)
        S.t(196 + 110 * v / mx + 6, yy, str(v), "m xs tx")

    # lifecycle
    ly = 640
    S.t(60, ly, "NODE LIFECYCLE · RUN BY SLERM-ORCH", "ey")
    states = ["serving", "model unloaded", "powered off", "waking"]
    arrows = ["idle 20 min · unload model, release CPU nodes",
              "idle 60 min · off via Proxmox API or BMC",
              "request arrives · gateway holds it"]
    pw, py = 130, ly + 22
    gapw = (1560 - 4 * pw) / 3
    xs = [60 + i * (pw + gapw) for i in range(4)]
    for i, s in enumerate(states):
        # the page lights each state in turn (CSS animation, staggered here)
        S.o.append(f'<rect x="{xs[i]:g}" y="{py:g}" width="{pw:g}" height="30" rx="15" class="pill p-state" '
                   f'style="animation-delay:{i * 2.5:g}s"/>')
        S.t(xs[i] + pw / 2, py + 19, s, "sm tx", "middle")
        if i < 3:
            a0, a1 = xs[i] + pw + 6, xs[i + 1] - 8
            S.line(a0, py + 15, a1, py + 15, "nt", marker=True)
            S.t((a0 + a1) / 2, py + 8, arrows[i], "m xs mu", "middle")
    x_last, x_first = xs[3] + pw / 2, xs[0] + pw / 2
    S.path(f"M{x_last},{py + 30} v18 q0,10 -10,10 H{x_first + 10} q-10,0 -10,-10 v-16", "nt", marker=True)
    S.t((x_first + x_last) / 2, py + 76, "nodes boot, the router loads the model, the held request is answered",
        "m xs mu", "middle")
    S.t(60, py + 112, "A VM started by hand on byteme pre-empts slerm through a Proxmox hookscript. "
        "When the UPS is on battery, byteme2 tells the head, and slerm freezes its jobs and stops waking nodes.", "sm")

    # ---- traffic: each client's request runs gateway -> router on node04 and back. Both GPUs are inside
    # node04 and no preset uses the CPU nodes, so nothing travels below the router.
    g = gy - 4
    for i, yc in enumerate(ys):
        S.packet([[(300, yc), (356, yc), (356, g), (hx - 2, g)],
                  [(hx + hw, g), (nx - 2, g)],
                  [(nx - 2, g), (hx + hw, g)],
                  [(hx - 2, g), (356, g), (356, yc), (300, yc)]],
                 ["violet"] * 2 + ["text"] * 2, speed=140, delay=i * 2.4, rest=9, hold=0.6)
    S.h = py + 140
    return S


# ------------------------------------------------ poster 3: power failure ---


def poster_power():
    W = 1680
    S = Svg(W, 900, "pwr", "Power failure timeline: after a 15 second grace, ups-guardian powers off byteme and "
            "deadlock and shuts byteme2's guests in parallel, all inside a 240 second deadline, well within the "
            "UPS runtime; DNS and the tailnet router keep running.")
    title_block(S, 62, "power failure", " · ups-guardian",
                f"CyberPower LX1500GAVR on USB to byteme2 · pwrstatd polls every 3 s · "
                f"~{POWER['runtime_min']} min of runtime at today's idle {POWER['ups_w']} W")

    X0, X1, T = 300, 1620, 360
    sx = (X1 - X0) / T

    def X(t):
        return X0 + t * sx

    S.t(60, 136, "FIRST MINUTES ON BATTERY · DRAWN TO SCALE", "ey")
    ax = 168
    lanes = [
        ("pwrstatd", "UPS reports mains lost"),
        ("blip filter", "cancel if mains return"),
        ("byteme", "Dell R730 · slerm GPUs"),
        ("deadlock", "slerm-node05"),
        ("byteme2 guests", "all at once"),
        ("byteme2 host", "HP DL360"),
        ("DNS + CFT", "Technitium · tailnet router"),
        ("Starlink + Wi-Fi", "network gear"),
        ("slerm", "orchestrator"),
    ]
    ly0, lstep = 206, 46
    lane_y = [ly0 + i * lstep for i in range(len(lanes))]
    bottom = lane_y[-1] + 22
    for t in range(0, T + 1, 30):
        S.line(X(t), ax + 8, X(t), bottom, "grid")
        S.t(X(t), ax, f"{t // 60}:{t % 60:02d}", "m xs mu", "middle")
    for (n, d), y in zip(lanes, lane_y):
        S.t(60, y, n, "nm")
        S.t(60, y + 16, d, "xs mu")

    def bar(y, t0, t1, cls, label, inside=False):
        S.rect(X(t0), y - 10, max(X(t1) - X(t0), 3), 14, cls, rx=3)
        if label:
            S.t(X(t1) + 10 if not inside else X(t0) + 8, y + 1, label, "sm" if not inside else "m xs seg-t")

    y = lane_y
    S.circle(X(0), y[0] - 3, 5, "st-run")
    S.t(X(0) + 14, y[0] + 1, "mains lost → ups-guardian onbatt; slerm is told at once", "sm")
    bar(y[1], 0, 15, "b-wait", "waits 15 s · short blips end here with nothing touched · skipped if the battery "
        "already reads low")
    bar(y[2], 15, 105, "b-off", "iDRAC soft power-off (Proxmox shuts its VMs) · forced off at 90 s if still up")
    bar(y[3], 15, 165, "b-off", "BMC soft power-off · 150 s to confirm")
    shed = sum(1 for g in BYTEME2_GUESTS if g[5] == "run" and g[1] not in PROTECTED)
    # 60 s for every guest, up to 180 s for Wuzah alone; the labels sit clear of the deadline line at 4:00
    bar(y[4], 15, 75, "b-off", "")
    bar(y[4], 75, 195, "b-wait", "")
    S.t(X(75) + 8, y[4] + 1, f"{shed} guests at once · 60 s grace (25 s with no agent, Wuzah 180 s)", "m xs tx")
    bar(y[5], 195, T, "b-keep", "")
    S.t(X(240) + 10, y[5] + 1, f"iLO power cap {POWER_CAP_W} W once the guests are down", "m xs seg-t")
    bar(y[6], 0, T, "b-keep", "keep running for DNS and remote access until low battery", inside=True)
    bar(y[7], 0, T, "b-keep", "stays up, and keeps going after byteme2 halts", inside=True)
    bar(y[8], 0, T, "b-slerm", "told at once and every 60 s · running jobs frozen · no node power-ons", inside=True)
    S.line(X(240), ax + 8, X(240), bottom + 8, "deadline")
    S.t(X(240) + 6, bottom + 22, "4 min hard deadline: anything still up is force-stopped", "m xs dl")
    S.t(X(T), ax - 22, f"ups-guardian is sized for ~{GUARDIAN_BUDGET_MIN} min of battery under load", "m xs mu", "end")
    # replay: the page sweeps this playhead across the first six minutes, dimming what hasn't happened yet
    S.o.append(f'<g class="ph" data-x0="{X0}" data-x1="{X1}" data-t="{T}">'
               f'<rect class="ph-veil" x="{X0}" y="{ax + 8}" width="{W - X0}" height="{bottom - ax + 20}"/>'
               f'<line class="ph-line" x1="{X0}" y1="{ax - 4}" x2="{X0}" y2="{bottom + 4}"/>'
               f'<rect class="ph-tag" x="{X0 - 22}" y="{ax - 15}" width="44" height="19" rx="9.5"/>'
               f'<text class="ph-t" x="{X0}" y="{ax - 1.5}" text-anchor="middle">0:00</text></g>')

    lb = bottom + 70
    S.t(60, lb, "LOW BATTERY", "ey")
    S.t(60, lb + 22, "At 35 % charge or under 5 min of runtime, judged once byteme is confirmed off: force-stop "
        "anything left, shut down Technitium and CFT, halt byteme2.", "sm")
    S.t(60, lb + 42, "Starlink and the Wi-Fi outlast it on the UPS, so the house keeps internet a while longer.", "sm")

    ry = lb + 86
    S.t(60, ry, "POWER BACK · RESTORE WATCHER CHECKS EVERY 15 S", "ey")
    steps = [
        ("Lift the cap", "byteme2's iLO power cap comes off"),
        ("Power on byteme", "via iDRAC, never within 150 s of the power-off"),
        ("Restart byteme's VMs", "pve-guest-restore: slerm-head first, then the rest"),
        ("Restart byteme2 guests", "exactly the list it stopped"),
        ("Power on deadlock", "via BMC once slerm-head answers (≤ 15 min)"),
    ]
    sw, sg = 288, (1560 - 5 * 288) / 4
    for i, (n, d) in enumerate(steps):
        x0 = 60 + i * (sw + sg)
        S.card(x0, ry + 16, sw, 64, "card frame")
        S.t(x0 + 14, ry + 40, f"{i + 1}", "m sm mu")
        S.t(x0 + 34, ry + 40, n, "nm")
        S.t(x0 + 14, ry + 62, d, "sm mu")
        if i < 4:
            S.line(x0 + sw + 3, ry + 48, x0 + sw + sg - 4, ry + 48, "nt", marker=True)
    S.t(60, ry + 106, "slerm is told power is back. If byteme doesn't answer, the watcher retries up to 20 times.", "sm")

    ny = ry + 150
    notes = [
        ("Disarm", ["A switch on the power dashboard mutes the", "response for up to 4 h. Low battery still acts."]),
        ("Tested", ["A dry run and a real outage test replay the", "whole sequence from the dashboard."]),
        ("Visible", ["The power dashboard opens an incident console;", "the Pi wall jumps to its outage scene."]),
        ("Last real ones", ["1 Oct: two planned pulls of the UPS plug.", "19 Sep: a 48 s blackout ran the full sequence."]),
    ]
    for i, (h, lines) in enumerate(notes):
        x0 = 60 + i * 396
        S.t(x0, ny, h.upper(), "ey")
        for j, l in enumerate(lines):
            S.t(x0, ny + 22 + j * 18, l, "sm")
    S.h = ny + 70
    return S


# -------------------------------------------------- figure: public edge -----


def figure_edge():
    W = 1360
    lanes = [
        ("Website status", "live lab numbers",
         [("Raspberry Pi 3B", "status API · Proxmox + UPS"), ("cloudflared on CFT", "tunnel to Cloudflare"),
          ("Worker nbdevlab", "reads it through the tunnel"), ("nbdevlab.com/status", "visitor's browser")],
         ["HTTP\non the LAN", "outbound\ntunnel", "JSON\nper visit"]),
        ("Weather", "Tempest on the site",
         [("Tempest station", "hub on Wi-Fi"), ("WeatherFlow API", "cloud REST"),
          ("Worker nbdevlab", "stores history in D1"), ("nbdevlab.com/weather", "visitor's browser")],
         ["uploads", "token auth", "JSON\n+ trends"]),
        ("Media", "home stays closed",
         [("Viewer", "anywhere"), ("Oracle VPS", "Caddy · Let's Encrypt"),
          ("Jellyfin VM", "isolated DMZ")],
         ["HTTPS", "WireGuard\ndialed from home"]),
        ("Admin · tailnet", "whole LAN, anywhere",
         [("Ghost or phone", "anywhere"), ("byteme2 · CFT", "subnet routers"),
          ("The lab", "names via Technitium")],
         ["Tailscale\ndirect WireGuard", "routed"]),
        ("Admin · browser", "UIs behind Access",
         [("Browser", "anywhere"), ("Cloudflare Access", "Zero Trust login"),
          ("cloudflared", "outbound tunnel"), ("Admin UIs", "on the LAN")],
         ["HTTPS", "tunnel", "LAN"]),
        ("VPS monitoring", "the VPS reports home",
         [("Oracle VPS", "Wazuh agent"), ("Wuzah", "Wazuh manager"),
          ("PMG", "mail gateway"), ("Brevo", "SMTP relay → inbox")],
         ["WireGuard\nagent traffic only", "serious\nalerts", "relay"]),
    ]
    step = 84
    S = Svg(W, 24 + len(lanes) * step, "edge", "How outside traffic reaches the lab and what the lab sends out: "
            "six paths, each a chain from source to destination with the transport on every hop.")
    m, cw = 16, 190
    x0 = m + 190
    gap = (W - m - x0 - 4 * cw) / 3
    for i, (name, sub, nodes, hops) in enumerate(lanes):
        y = 16 + i * step
        S.t(m, y + 24, name, "nm")
        S.t(m, y + 42, sub, "sm mu")
        hops_xy = []
        for j, (n, d) in enumerate(nodes):
            x = x0 + j * (cw + gap)
            S.card(x, y, cw, 56, "card frame")
            S.t(x + 14, y + 24, n, "nm")
            S.t(x + 14, y + 42, d, "sm mu")
            if j < len(nodes) - 1:
                a0, a1 = x + cw + 6, x + cw + gap - 8
                S.line(a0, y + 28, a1, y + 28, "nt", marker=True)
                hops_xy.append([(a0, y + 28), (a1 - 4, y + 28)])
                top_l, _, bottom_l = hops[j].partition("\n")
                S.t((a0 + a1) / 2, y + 20, top_l, "m xs mu", "middle")
                if bottom_l:
                    S.t((a0 + a1) / 2, y + 44, bottom_l, "m xs mu", "middle")
        if i < len(lanes) - 1:
            S.hr(m, W - m, y + step - 12)
        S.packet(hops_xy, "text", speed=110, delay=i * 1.15, rest=2.5, hold=0.1)
    return S


# ------------------------------------------------------------------- page ---

CSS = """
:root {
  /* Layout: one long page on pitch black. Open bands split by hairlines; figures fill the column and
     can switch to full size with sideways scroll. Colour means network, violet means slerm. */
  --bg: #000000;
  --card: #06080c;
  --raise: #0e1118;
  --line: #1b2029;
  --line-2: #2a313d;
  --text: #e7ecf3;
  --text-2: #a4aebd;
  --muted: #677284;
  --accent: #8ea8ff;
  --violet: #b69bff;
  --violet-wash: rgba(182,155,255,.12);
  --lan: #3ddc97;
  --mgmt: #f3b64b;
  --srv: #8ea8ff;
  --dmz: #ff7a90;
  --bad: #ff6b6b;
  --sans: "Geist", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "Geist Mono", ui-monospace, "JetBrains Mono", Menlo, Consolas, monospace;
  --ease: cubic-bezier(.2,.8,.2,1);
  color-scheme: dark;
}
html, body { background: var(--bg); color: var(--text); }
body { margin: 0; font: 15px/1.55 var(--sans); -webkit-font-smoothing: antialiased; }

/* svg */
.pz { display: block; height: auto; }
.pz text { font-family: var(--sans); font-size: 12.5px; fill: var(--text-2); }
.pz .m { font-family: var(--mono); font-size: 11px; }
.pz .sm { font-size: 12.5px; }
.pz .xs { font-size: 10.5px; }
.pz .ey { font-size: 10px; letter-spacing: .14em; font-weight: 500; fill: var(--muted); }
.pz .ti { font-size: 17px; font-weight: 600; fill: var(--text); letter-spacing: -.01em; }
.pz .nm { font-size: 13px; font-weight: 600; fill: var(--text); }
.pz .big { font-size: 30px; font-weight: 600; fill: var(--text); letter-spacing: -.02em; }
.pz .mu, .pz tspan.mu { fill: var(--muted); }
.pz .tx { fill: var(--text); }
.pz .card { fill: var(--card); stroke: var(--line-2); stroke-width: 1; }
.pz .frame { fill: none; }
.pz .card-hi { stroke: #3a4352; }
.pz .parked-card { stroke-dasharray: 4 4; }
.pz .hr { stroke: var(--line); stroke-width: 1; }
.pz .grid { stroke: var(--line); stroke-width: 1; }
.pz .w { fill: none; stroke-width: 2.25; stroke-linecap: round; }
.pz .stub { fill: none; stroke-width: 3; stroke-linecap: round; }
.pz .halo { fill: none; stroke: var(--bg); stroke-width: 9; }
.pz .nt { fill: none; stroke: var(--muted); stroke-width: 1.25; }
.pz .dash { stroke-dasharray: 5 5; }
.pz .req { fill: none; stroke: var(--violet); stroke-width: 1.75; }
.pz .ah { fill: var(--muted); }
.pz .pw-b { fill: none; stroke: var(--text-2); stroke-width: 2; }
.pz .pw-s { fill: none; stroke: var(--muted); stroke-width: 1.5; stroke-dasharray: 3 4; }
.pz .psu { fill: var(--text-2); }
.pz .st-run { fill: var(--text); }
.pz .st-off { fill: var(--bg); stroke: var(--text-2); stroke-width: 1.25; }
.pz .pill { fill: none; stroke-width: 1; }
.pz .p-tun { stroke: var(--line-2); }
.pz .pt-tun { fill: var(--text-2); }
.pz .p-slerm { stroke: var(--violet); }
.pz .pt-slerm { fill: var(--violet); }
.pz .p-state { stroke: var(--line-2); fill: var(--card); }
.pz .s-lan { stroke: var(--lan); } .pz .f-lan { fill: var(--lan); }
.pz .s-mgmt { stroke: var(--mgmt); } .pz .f-mgmt { fill: var(--mgmt); }
.pz .s-srv { stroke: var(--srv); } .pz .f-srv { fill: var(--srv); }
.pz .s-dmz { stroke: var(--dmz); } .pz .f-dmz { fill: var(--dmz); }
.pz .seg { stroke: none; }
.pz .gpu1 { fill: var(--violet); } .pz .gpu2 { fill: #8f74e0; }
.pz .cpu1 { fill: #5d6678; } .pz .cpu2 { fill: #4b5364; } .pz .cpu3 { fill: #7a8499; }
.pz .seg-t { fill: #0b0d12; font-weight: 500; }
.pz .bar { fill: var(--violet); }
.pz .b-wait { fill: #3a4352; }
.pz .b-off { fill: var(--text-2); }
.pz .b-keep { fill: #1c2230; stroke: var(--line-2); }
.pz .b-slerm { fill: rgba(182,155,255,.16); stroke: rgba(182,155,255,.45); }
.pz .b-keep + text, .pz .b-slerm + text { fill: var(--text-2); }
.pz .deadline { stroke: var(--bad); stroke-width: 1.5; stroke-dasharray: 4 3; }
.pz .dl { fill: var(--bad); }

/* motion: packets ride the wires, running dots breathe, tunnels march, the outage replays.
   Everything here is off unless the page sets .motion on the root, so the PNG posters stay still. */
.pz .pk { pointer-events: none; }
:root:not(.motion) .pz .pk { display: none; }
.pz .pk-c { fill: currentColor; }
.pz .pk-h { fill: currentColor; opacity: .2; }
.pz .k-text { color: var(--text); } .pz .k-power { color: var(--text-2); } .pz .k-violet { color: var(--violet); }
.pz .k-lan { color: var(--lan); } .pz .k-mgmt { color: var(--mgmt); }
.pz .k-srv { color: var(--srv); } .pz .k-dmz { color: var(--dmz); }
.pz .ph { display: none; pointer-events: none; transition: opacity .6s var(--ease); }
.motion .pz .ph.on { display: inline; }
.pz .ph-veil { fill: var(--bg); opacity: .62; }
.pz .ph-line { stroke: var(--text); stroke-width: 1.25; }
.pz .ph-tag { fill: var(--text); }
.pz .ph-t { font-family: var(--mono); font-size: 10.5px; font-weight: 500; fill: var(--bg); }
.motion .pz .st-run { animation: breathe 3.6s ease-in-out infinite; }
.motion .pz .dash { animation: march 1.6s linear infinite; }
.motion .pz .p-state { animation: state-on 10s linear infinite; }
@keyframes breathe { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
@keyframes march { to { stroke-dashoffset: 10; } }
@keyframes state-on {
  0%, 22% { stroke: var(--violet); fill: var(--violet-wash); }
  26%, 100% { stroke: var(--line-2); fill: var(--card); }
}

/* scroll reveal: the page hides only what starts below the fold (.rv-on on the root), then builds each
   diagram as it scrolls in. Cards rise, wires draw, bars grow, text settles; traffic starts when it's done. */
.rv-on .pz .rv-s { opacity: 0; animation: none; }
.rv-on .pz .rv-in { animation: rv-fade .55s var(--ease) both; }
.rv-on .pz text.rv-in { animation-name: rv-rise; animation-duration: .65s; }
.rv-on .pz .card.rv-in { animation: rv-card .75s var(--ease) both; transform-box: fill-box; transform-origin: 50% 50%; }
.rv-on .pz line.rv-in.w, .rv-on .pz line.rv-in.req, .rv-on .pz line.rv-in.pw-b,
.rv-on .pz line.rv-in.nt:not(.dash), .rv-on .pz path.rv-in.nt {
  stroke-dasharray: var(--len) var(--len); animation: rv-draw .95s var(--ease) both; }
.rv-on .pz .rv-in.b-wait, .rv-on .pz .rv-in.b-off, .rv-on .pz .rv-in.b-keep, .rv-on .pz .rv-in.b-slerm,
.rv-on .pz .rv-in.bar, .rv-on .pz .rv-in.seg {
  animation: rv-grow .9s var(--ease) both; transform-box: fill-box; transform-origin: 0 50%; }
.rv-on .pz.rv-pending .pk, .rv-on .pz.rv-pending .ph { visibility: hidden; }
@keyframes rv-fade { from { opacity: 0; } }
@keyframes rv-rise { from { opacity: 0; translate: 0 8px; } }
@keyframes rv-card { from { opacity: 0; scale: .96; } }
@keyframes rv-draw { 0% { stroke-dashoffset: var(--len); opacity: 0; } 25% { opacity: 1; } }
@keyframes rv-grow { from { scale: 0 1; } }
"""

PAGE_CSS = """
.wrap { max-width: 1320px; margin: 0 auto; padding-inline: 24px; }
@media (max-width: 600px) { .wrap { padding-inline: 16px; } }
header.top { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 5; background: rgba(0,0,0,.86);
  backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); }
header.top .wrap { display: flex; gap: 20px; align-items: center; justify-content: space-between; min-height: 52px; flex-wrap: wrap; }
.brand { font-weight: 600; letter-spacing: -.01em; font-size: 15px; }
.brand i { font-style: normal; color: var(--accent); }
nav.jump { display: flex; gap: 4px; flex-wrap: wrap; }
nav.jump a { color: var(--text-2); text-decoration: none; font-size: 13px; padding: 5px 9px; border-radius: 7px; }
nav.jump a:hover, nav.jump a:focus-visible { background: var(--raise); color: var(--text); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.hero { padding-block: 56px 28px; }
.eyebrow { font: 500 11px/1 var(--mono); letter-spacing: .14em; text-transform: uppercase; color: var(--muted); }
h1 { font-size: clamp(34px, 5vw, 56px); line-height: 1.02; letter-spacing: -.035em; margin: 14px 0 16px; font-weight: 600; text-wrap: balance; }
h1 span { color: var(--muted); font-weight: 500; }
.lede { max-width: 68ch; color: var(--text-2); font-size: 16.5px; margin: 0; }

.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(128px, 1fr)); border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line); margin-top: 32px; }
.stat { padding: 16px 16px 14px 0; min-width: 0; }
.stat + .stat { padding-left: 16px; border-left: 1px solid var(--line); }
@media (max-width: 700px) { .stat + .stat { border-left: 0; padding-left: 0; } }
.stat b { display: block; font: 600 26px/1.1 var(--sans); letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.stat span { font-size: 12.5px; color: var(--muted); }

.controls { display: flex; gap: 10px 22px; flex-wrap: wrap; align-items: center; padding-block: 16px; color: var(--text-2); font-size: 13.5px; }
.switch { display: inline-flex; align-items: center; gap: 9px; cursor: pointer; user-select: none; }
.switch input { appearance: none; width: 32px; height: 18px; border-radius: 9px; background: var(--line-2); position: relative; margin: 0; cursor: pointer; transition: background .2s var(--ease); }
.switch input::after { content: ""; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: var(--text); transition: transform .2s var(--ease); }
.switch input:checked { background: var(--accent); }
.switch input:checked::after { transform: translateX(14px); }
.seg-ctl { display: inline-flex; border: 1px solid var(--line-2); border-radius: 8px; overflow: hidden; }
.seg-ctl button { background: none; border: 0; color: var(--text-2); font: inherit; font-size: 13px; padding: 5px 11px; cursor: pointer; }
.seg-ctl button[aria-pressed="true"] { background: var(--raise); color: var(--text); }

section.band { border-top: 1px solid var(--line); padding-block: 40px 44px; scroll-margin-top: 64px; }
section.band h2 { font-size: 24px; letter-spacing: -.02em; margin: 8px 0 10px; font-weight: 600; }
section.band p { max-width: 70ch; color: var(--text-2); margin: 0 0 14px; }
section.band > h3 { font-size: 18px; letter-spacing: -.01em; margin: 34px 0 8px; font-weight: 600; }
figure { margin: 22px 0 0; }
.fig-scroll { overflow-x: auto; overscroll-behavior-x: contain; }
.fig-scroll .pz { width: 100%; }
.full .fig-scroll .pz { width: auto; max-width: none; }
figcaption { color: var(--muted); font-size: 13px; margin-top: 12px; max-width: 80ch; }

ol.seq { margin: 0; padding: 0; list-style: none; counter-reset: s; max-width: 80ch; }
ol.seq li { counter-increment: s; display: grid; grid-template-columns: 34px 1fr; gap: 6px; padding: 9px 0; border-bottom: 1px solid var(--line); color: var(--text-2); }
ol.seq li::before { content: counter(s); font: 500 12px/1.9 var(--mono); color: var(--muted); }
ol.seq b { color: var(--text); font-weight: 600; }

.table-scroll { overflow-x: auto; margin-top: 18px; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; min-width: 860px; }
th { text-align: left; font: 500 10.5px/1 var(--mono); letter-spacing: .12em; text-transform: uppercase; color: var(--muted);
  padding: 10px 14px 10px 0; border-bottom: 1px solid var(--line-2); white-space: nowrap; }
td { padding: 10px 14px 10px 0; border-bottom: 1px solid var(--line); vertical-align: top; color: var(--text-2); }
td:first-child { color: var(--text); font-weight: 600; white-space: nowrap; }
td.num, td .mono, .mono { font-family: var(--mono); font-size: 12.5px; font-variant-numeric: tabular-nums; }
td.sub { color: var(--muted); font-weight: 400; }
.net { display: inline-flex; align-items: center; gap: 7px; white-space: nowrap; }
.net::before { content: ""; width: 12px; height: 3px; border-radius: 2px; background: var(--c); }
.tag { display: inline-block; font: 500 11px/1 var(--mono); padding: 3px 7px; border: 1px solid var(--line-2); border-radius: 999px; color: var(--text-2); margin-right: 4px; }
.tag.slerm { border-color: var(--violet); color: var(--violet); }
.state { font: 12px var(--mono); white-space: nowrap; }
.state::before { content: ""; display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 7px; background: var(--text); vertical-align: 1px; }
.state.off::before { background: none; box-shadow: inset 0 0 0 1.25px var(--text-2); }

.rules { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 0 40px; margin-top: 22px; }
.rules div { border-top: 1px solid var(--line); padding-block: 16px 18px; min-width: 0; }
.rules h3 { font-size: 15px; font-weight: 600; letter-spacing: -.01em; margin: 0 0 6px; }
.rules p { font-size: 14px; color: var(--text-2); margin: 0; }
ol.log { list-style: none; margin: 18px 0 0; padding: 0; max-width: 80ch; }
ol.log li { display: grid; grid-template-columns: 72px 1fr; gap: 12px; padding-block: 11px; border-bottom: 1px solid var(--line); color: var(--text-2); }
ol.log time { font: 500 12px/1.9 var(--mono); color: var(--muted); font-variant-numeric: tabular-nums; }
ol.log li.next time { color: var(--accent); }

/* scroll reveal for the page around the diagrams: blocks settle out of a blur, section hairlines draw across */
.rv-on .rv-b { opacity: 0; translate: 0 18px; filter: blur(6px); }
.rv-on tr.rv-b { filter: none; translate: 0 10px; }
.rv-on .rv-b.rv-go { opacity: 1; translate: 0 0; filter: blur(0);
  transition: opacity .8s var(--ease), translate 1s var(--ease), filter .8s var(--ease); transition-delay: var(--d, 0s); }
.rv-on section.band { border-top-color: transparent; position: relative; }
.rv-on section.band::before { content: ""; position: absolute; inset: -1px 0 auto 0; height: 1px; background: var(--line);
  transform-origin: 0 50%; transition: transform 1.4s var(--ease); }
.rv-on section.band.rv-line::before { transform: scaleX(0); }

.parked { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 22px 36px; margin-top: 26px; }
.parked h3 { font: 500 11px/1 var(--mono); letter-spacing: .12em; text-transform: uppercase; color: var(--muted); margin: 0 0 10px; }
.parked p { font-size: 13.5px; color: var(--text-2); margin: 0; }
footer { border-top: 1px solid var(--line); padding-block: 28px 48px; color: var(--muted); font-size: 13px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700'
         '&family=Geist+Mono:wght@400;500&display=swap">')

JS = r"""
(function () {
  var root = document.documentElement;
  var motionBox = document.getElementById('toggle-motion');
  var size = document.querySelectorAll('.seg-ctl button');
  function load(k, d) { try { var v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function setSize(mode) {
    root.classList.toggle('full', mode === 'full');
    size.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.size === mode)); });
    save('hm-size', mode);
  }
  size.forEach(function (b) { b.addEventListener('click', function () { setSize(b.dataset.size); }); });
  setSize(load('hm-size', 'fit'));

  // ---- motion. Packets are <g class="pk"> elements whose data-legs hold polylines ("x,y x,y;x,y x,y").
  // A packet walks each leg at data-speed (svg units/s) and is hidden between legs, as if crossing a box.
  var packets = [], heads = [], visible = new Map();
  function pts(str) { return str.trim().split(/\s+/).map(function (p) { var a = p.split(','); return [+a[0], +a[1]]; }); }
  function dist(a, b) { return Math.hypot(b[0] - a[0], b[1] - a[1]); }
  document.querySelectorAll('svg.pz').forEach(function (svg) {
    var pk = svg.querySelectorAll('.pk'), ph = svg.querySelectorAll('.ph');
    if (!pk.length && !ph.length) return;
    visible.set(svg, false);
    pk.forEach(function (g) {
      var speed = +g.dataset.speed, hold = +g.dataset.hold, colors = g.dataset.c.split(' ');
      var legs = g.dataset.legs.split(';').map(function (str, i) {
        var p = pts(str), cum = [0];
        for (var k = 1; k < p.length; k++) cum.push(cum[k - 1] + dist(p[k - 1], p[k]));
        return { p: p, cum: cum, len: cum[cum.length - 1], c: colors[i] || colors[0] };
      });
      var segs = [], t = 0;
      legs.forEach(function (L, i) {
        var d = Math.max(L.len / speed, 0.05);
        segs.push({ leg: L, t0: t, d: d });
        t += d;
        if (i < legs.length - 1) t += Math.min(dist(L.p[L.p.length - 1], legs[i + 1].p[0]) / speed, 0.5) + hold;
      });
      packets.push({ svg: svg, g: g, segs: segs, period: t + (+g.dataset.rest), delay: +g.dataset.delay, cls: '' });
    });
    ph.forEach(function (g) {
      var veil = g.querySelector('.ph-veil');
      heads.push({ svg: svg, g: g, x0: +g.dataset.x0, x1: +g.dataset.x1, T: +g.dataset.t, veil: veil,
        right: +veil.getAttribute('x') + +veil.getAttribute('width'), line: g.querySelector('.ph-line'),
        tag: g.querySelector('.ph-tag'), txt: g.querySelector('.ph-t'), start: null, label: '' });
    });
  });

  function at(L, s) {
    var k = 1;
    while (k < L.cum.length - 1 && L.cum[k] < s) k++;
    var a = L.p[k - 1], b = L.p[k], f = (s - L.cum[k - 1]) / ((L.cum[k] - L.cum[k - 1]) || 1);
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
  }
  function drawPacket(P, now) {
    var u = ((now + P.delay) % P.period + P.period) % P.period;
    for (var i = 0; i < P.segs.length; i++) {
      var S = P.segs[i];
      if (u >= S.t0 && u < S.t0 + S.d) {
        var s = (u - S.t0) / S.d * S.leg.len, xy = at(S.leg, s);
        P.g.setAttribute('transform', 'translate(' + xy[0].toFixed(1) + ' ' + xy[1].toFixed(1) + ')');
        P.g.style.opacity = Math.max(0, Math.min(1, s / 10, (S.leg.len - s) / 10)).toFixed(2);
        var cls = 'pk k-' + S.leg.c;
        if (cls !== P.cls) { P.g.setAttribute('class', cls); P.cls = cls; }
        return;
      }
    }
    P.g.style.opacity = 0;
  }
  var SWEEP = 16, REST = 3;  // seconds: replay the first six minutes in 16 s, then show the whole chart
  function drawHead(H, now) {
    if (H.svg.classList.contains('rv-pending')) return;  // the replay waits until the chart has built
    if (H.start === null) { H.start = now; H.g.classList.add('on'); }
    var u = (now - H.start) % (SWEEP + REST), f = Math.min(u / SWEEP, 1);
    var x = H.x0 + f * (H.x1 - H.x0), sec = Math.round(f * H.T);
    H.g.style.opacity = u < SWEEP ? 1 : 0;
    H.veil.setAttribute('x', x.toFixed(1));
    H.veil.setAttribute('width', Math.max(0, H.right - x).toFixed(1));
    H.line.setAttribute('x1', x.toFixed(1));
    H.line.setAttribute('x2', x.toFixed(1));
    H.tag.setAttribute('x', (x - 22).toFixed(1));
    H.txt.setAttribute('x', x.toFixed(1));
    var label = Math.floor(sec / 60) + ':' + String(sec % 60).padStart(2, '0');
    if (label !== H.label) { H.txt.textContent = label; H.label = label; }
  }

  var raf = 0, t0 = performance.now();
  function frame(ts) {
    raf = 0;
    if (!root.classList.contains('motion')) return;
    var now = (ts - t0) / 1000, any = false;
    packets.forEach(function (P) { if (visible.get(P.svg)) { drawPacket(P, now); any = true; } });
    heads.forEach(function (H) { if (visible.get(H.svg)) { drawHead(H, now); any = true; } });
    if (any) raf = requestAnimationFrame(frame);
  }
  function kick() { if (!raf && root.classList.contains('motion')) raf = requestAnimationFrame(frame); }
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { visible.set(e.target, e.isIntersecting); });
      kick();
    }, { rootMargin: '120px 0px' });
    visible.forEach(function (_, svg) { io.observe(svg); });
  } else {
    visible.forEach(function (_, svg) { visible.set(svg, true); });
  }

  var reduce = false;
  try { reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) {}
  function setMotion(on, remember) {
    root.classList.toggle('motion', on);
    motionBox.checked = on;
    if (remember) save('hm-motion', on ? '1' : '0');
    kick();
  }
  motionBox.addEventListener('change', function () { setMotion(motionBox.checked, true); });
  setMotion(load('hm-motion', reduce ? '0' : '1') === '1', false);

  // ---- scroll reveal. Runs once, only with motion on, and only hides what starts below the fold, so the
  // first screen is always complete. Diagram parts reveal one by one as their own height crosses the line,
  // left to right within a row; text blocks and table rows settle in as they enter.
  var BLOCKS = '.band > .eyebrow, .band > h2, .band > p, figcaption, .rules > div, ol.log li, .parked > div, ' +
               '.table-scroll tr, footer .wrap';
  var builds = [], blockIo = null;
  function revealLine() { return window.innerHeight * 0.9; }
  function startReveal() {
    if (!('IntersectionObserver' in window)) return;
    var L = revealLine();
    blockIo = new IntersectionObserver(function (entries) {
      var k = 0;
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        blockIo.unobserve(el);
        if (el.tagName === 'SECTION') { el.classList.remove('rv-line'); return; }
        el.style.setProperty('--d', Math.min(k++ * 0.07, 0.5) + 's');
        el.classList.add('rv-go');
      });
    }, { rootMargin: '0px 0px -8% 0px' });
    document.querySelectorAll(BLOCKS).forEach(function (el) {
      if (el.getBoundingClientRect().top < L) return;
      el.classList.add('rv-b');
      blockIo.observe(el);
    });
    document.querySelectorAll('section.band').forEach(function (el) {
      if (el.getBoundingClientRect().top < L) return;
      el.classList.add('rv-line');
      blockIo.observe(el);
    });
    document.querySelectorAll('svg.pz').forEach(function (svg) {
      var vb = svg.viewBox.baseVal, r = svg.getBoundingClientRect(), sc = r.height / vb.height, items = [];
      if (r.bottom < L) return;
      [].forEach.call(svg.children, function (el) {
        var tag = el.tagName.toLowerCase(), bb;
        if (tag === 'defs' || el.classList.contains('pk') || el.classList.contains('ph')) return;
        try { bb = el.getBBox(); } catch (e) { return; }
        if (r.top + bb.y * sc < L) return;
        if (tag === 'line' || tag === 'path') {
          try { el.style.setProperty('--len', el.getTotalLength().toFixed(1)); } catch (e) {}
        }
        if (el.style.animationDelay) el.dataset.rvDelay = el.style.animationDelay;
        el.classList.add('rv-s');
        items.push({ el: el, x: bb.x, y: bb.y });
      });
      if (!items.length) return;
      items.sort(function (a, b) { return a.y - b.y; });
      svg.classList.add('rv-pending');
      builds.push({ svg: svg, items: items, i: 0, w: vb.width, h: vb.height });
    });
    root.classList.add('rv-on');
    if (builds.length) {
      window.addEventListener('scroll', onScroll, { passive: true });
      window.addEventListener('resize', onScroll);
      onScroll();
    }
  }
  var ticking = false;
  function onScroll() { if (!ticking) { ticking = true; requestAnimationFrame(sweep); } }
  function sweep() {
    ticking = false;
    var L = revealLine();
    builds = builds.filter(function (B) {
      var r = B.svg.getBoundingClientRect(), sc = r.height / B.h;
      while (B.i < B.items.length && r.top + B.items[B.i].y * sc < L) {
        var it = B.items[B.i++];
        it.el.style.animationDelay = (it.x / B.w * 0.45).toFixed(3) + 's';
        it.el.classList.remove('rv-s');
        it.el.classList.add('rv-in');
      }
      if (B.i < B.items.length) return true;
      setTimeout(function () { B.svg.classList.remove('rv-pending'); kick(); }, 1000);
      return false;
    });
    if (!builds.length) {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    }
  }
  // once an element has settled, give it back its resting style (and the breathing dots their own stagger)
  document.addEventListener('animationend', function (e) {
    var el = e.target;
    if (!el.classList || !el.classList.contains('rv-in')) return;
    el.classList.remove('rv-in');
    el.style.removeProperty('--len');
    el.style.animationDelay = el.dataset.rvDelay || '';
  });
  document.addEventListener('transitionend', function (e) {
    var el = e.target;
    if (e.propertyName !== 'translate' || !el.classList || !el.classList.contains('rv-go')) return;
    el.classList.remove('rv-b', 'rv-go');
    el.style.removeProperty('--d');
  });
  function stopReveal() {
    root.classList.remove('rv-on');
    if (blockIo) blockIo.disconnect();
    builds.forEach(function (B) { B.svg.classList.remove('rv-pending'); });
    builds = [];
  }
  motionBox.addEventListener('change', function () { if (!motionBox.checked) stopReveal(); });
  if (root.classList.contains('motion')) startReveal();
})();
"""


def net_cell(net):
    return f'<span class="net" style="--c: var(--{net})">{esc(NETS[net][0])}</span>'


def guest_rows():
    rows = []
    for host, guests in (("byteme2", BYTEME2_GUESTS), ("byteme", BYTEME_GUESTS)):
        for kind, name, role, net, bdg, state, ram, disk in guests:
            tags = "".join(f'<span class="tag{" slerm" if b == "slerm" else ""}">{esc(b)}</span>' for b in bdg)
            st = '<span class="state">running</span>' if state == "run" else '<span class="state off">on demand</span>'
            disk_s = f"{disk / 1000:.1f} TB" if disk >= 1000 else f"{disk} GB"
            rows.append(
                f"<tr><td>{esc(name)}</td><td class='num'>{kind}</td><td>{esc(host)}</td><td>{st}</td>"
                f"<td>{esc(role)}</td><td>{net_cell(net)}</td>"
                f"<td class='num'>{ram:g} GB</td><td class='num'>{disk_s}</td><td>{tags}</td></tr>")
    rows.append("<tr><td>slerm-node05</td><td class='num'>metal</td><td>deadlock</td>"
                "<td><span class='state off'>on demand</span></td><td>CPU worker · the RAM node</td>"
                f"<td>{net_cell('srv')}</td><td class='num'>32 GB</td>"
                "<td class='num'>2.6 TB</td><td><span class='tag slerm'>slerm</span></td></tr>")
    rows.append("<tr><td>slerm-node03</td><td class='num'>VM</td><td>byteme3</td>"
                "<td><span class='state off'>parked</span></td><td>CPU worker · off with its host</td>"
                f"<td>{net_cell('srv')}</td><td class='num'>20 GB</td>"
                "<td class='num'>40 GB</td><td><span class='tag slerm'>slerm</span></td></tr>")
    return "\n".join(rows)


def parked_html():
    return "".join(f"<div><h3>{esc(title)} · {n}</h3><p>{esc(text)}</p></div>" for title, n, text in PARKED_PUBLIC)


def hardware_rows():
    rows = []
    for m, role, plat, cpu, mem, disk, net, pwr in HARDWARE:
        first = f"<td>{esc(m)}</td>" if m else "<td class='sub'>↳</td>"
        rows.append(f"<tr>{first}<td>{esc(role)}</td><td>{esc(plat)}</td><td>{esc(cpu)}</td>"
                    f"<td class='num'>{esc(mem)}</td><td>{esc(disk)}</td><td>{esc(net)}</td><td>{esc(pwr)}</td></tr>")
    return "\n".join(rows)


def figure(svg, caption):
    return f'<figure><div class="fig-scroll">{svg}</div><figcaption>{esc(caption)}</figcaption></figure>'


TITLE = "nbdevlab Homelab Map"
DESCRIPTION = ("Two Proxmox servers, a bare-metal RAM node and slerm, a Slurm cluster with two Tesla P100s, drawn as "
               "animated network, cluster, power-failure and public-edge diagrams.")


def body(p1, pw, p2, p3, fe):
    running = sum(1 for g in BYTEME2_GUESTS + BYTEME_GUESTS if g[5] == "run")
    defined = len(BYTEME2_GUESTS) + len(BYTEME_GUESTS) + sum(PARKED_COUNT.values())
    total_w = POWER["ups_w"] + SURGE_W
    stats = [
        ("3", "servers + one parked"), ("144", "CPU threads in service"),
        ("160 GB", "RAM across the servers"),
        ("12 TiB", "ZFS raw, two raidz1 pools"), ("2", "GPUs · 32 GB VRAM"),
        (f"{running}", f"guests running of {defined}", "guests"), (f"≈{total_w} W", "at the wall · snapshot", "wall-power"),
    ]
    # data-live marks a stat the website refreshes from its status feed; the standalone page keeps the snapshot.
    stats_html = "".join(
        f"<div class='stat'{' data-live=' + chr(39) + st[2] + chr(39) if len(st) > 2 else ''}>"
        f"<b>{esc(st[0])}</b><span>{esc(st[1])}</span></div>" for st in stats)
    rules_html = "".join(f"<div><h3>{esc(h)}</h3><p>{esc(t)}</p></div>" for h, t in SECURITY)
    log_html = "".join(
        f"<li{' class=\"next\"' if i == 0 and what.startswith('Next') else ''}><time>{esc(d)}</time>"
        f"<span>{esc(what)}</span></li>" for i, (d, what) in enumerate(CHANGES))
    return f"""<header class="top"><div class="wrap">
  <div class="brand">nbdevlab <i>/</i> homelab</div>
  <nav class="jump" aria-label="Sections">
    <a href="#map">Map</a><a href="#slerm">slerm</a><a href="#power">Power failure</a><a href="#edge">Public edge</a>
    <a href="#security">Security</a><a href="#hardware">Hardware</a><a href="#guests">Guests</a><a href="#changes">Changes</a>
  </nav>
</div></header>
<main class="wrap">
  <div class="hero">
    <div class="eyebrow">Homelab · snapshot {SNAPSHOT}</div>
    <h1>nbdevlab <span>homelab</span></h1>
    <p class="lede">Two Proxmox servers and a bare-metal RAM node behind a WatchGuard Firebox on Starlink, with a third
    Proxmox host parked for now. They run the house services, a SIEM, a mail gateway and slerm, a Slurm cluster
    I built to learn Slurm end to end. Cloudflare, one Oracle VPS and Tailscale handle everything that comes in
    from outside, and one UPS decides what happens when the power goes out.</p>
    <div class="stats">{stats_html}</div>
    <div class="controls">
      <label class="switch" for="toggle-motion"><input type="checkbox" id="toggle-motion" checked> Animate traffic</label>
      <span class="seg-ctl" role="group" aria-label="Diagram size">
        <button type="button" data-size="fit" aria-pressed="true">Fit width</button>
        <button type="button" data-size="full" aria-pressed="false">Full size</button>
      </span>
    </div>
  </div>

  <section class="band" id="map">
    <div class="eyebrow">01 · Topology</div>
    <h2>The map</h2>
    <p>Every network hangs off the Firebox. Colored lines are the four networks, and each guest's short color
    stub says which one it sits on. Dashed lines at the top are outbound tunnels. The rails at the bottom show
    which PSU of each server is on UPS battery.</p>
    {figure(p1, "Internet services, the edge, four networks, three servers with their running guests, a parked fourth, LAN devices and UPS wiring. The moving dots trace typical paths, such as a site visitor's status request reaching CFT or a stream reaching Jellyfin. They are examples, not live traffic.")}
  </section>

  <section class="band" id="slerm">
    <div class="eyebrow">02 · Cluster</div>
    <h2>slerm</h2>
    <p>slerm is a Slurm cluster made of VMs on the Proxmox servers plus deadlock, built to learn Slurm end to end.
    The head runs Slurm, a control panel that submits and schedules jobs, and the NFS share every node mounts.
    Everything else is a Slurm job: NOAA radar processing, Wazuh alert analysis, software builds and local LLM
    serving.</p>
    {figure(pw, "Each row is one workload, from where its data comes from to what it produces. The partition pills show where its jobs may run.")}
    <h3>LLM serving</h3>
    <p>Every LLM client talks to one OpenAI-style gateway on the head. The gateway starts a llama.cpp router on
    node04, which holds both Tesla P100s. A model that fits in their 32 GB runs on one card or across both. A bigger
    one keeps its overflow on node04's own CPUs. When nothing is asking, the model is unloaded and then the nodes
    power off. A request wakes them again.</p>
    {figure(p2, "Request path in violet, answers in white. In this snapshot only the head is running, so the first request wakes node04. The split bars come from the model presets and the speeds are measured through the gateway.")}
  </section>

  <section class="band" id="power">
    <div class="eyebrow">03 · Power</div>
    <h2>Power failure</h2>
    <p>The UPS carries one PSU of each server. When it reports mains lost, ups-guardian on byteme2 sheds everything
    it can within four minutes. It keeps DNS and the tailnet router up so the lab stays reachable, and puts
    it all back when mains return.</p>
    {figure(p3, "Timeline drawn to scale from ups-guardian's own timeouts. Bars show the longest each step is allowed to take. The playhead replays the first six minutes in sixteen seconds.")}
  </section>

  <section class="band" id="edge">
    <div class="eyebrow">04 · Outside</div>
    <h2>Public edge</h2>
    <p>How outside traffic reaches the lab and what the lab sends out. The website never talks to the house
    directly: the Worker reads the Pi's status API through a Cloudflare tunnel, and media goes through the VPS.</p>
    {figure(fe, "Six paths, each drawn from source to destination with the transport on every hop.")}
  </section>

  <section class="band" id="security">
    <div class="eyebrow">05 · Security</div>
    <h2>How it stays closed</h2>
    <p>The rules the layout above follows.</p>
    <div class="rules">{rules_html}</div>
  </section>

  <section class="band" id="hardware">
    <div class="eyebrow">06 · Specs</div>
    <h2>Hardware</h2>
    <div class="table-scroll"><table>
      <thead><tr><th>Machine</th><th>Role</th><th>Platform</th><th>CPU</th><th>RAM</th><th>Storage</th><th>Network</th><th>Power</th></tr></thead>
      <tbody>{hardware_rows()}</tbody>
    </table></div>
  </section>

  <section class="band" id="guests">
    <div class="eyebrow">07 · Inventory</div>
    <h2>Guests</h2>
    <p>{running} guests running, three slerm VMs that start on demand, deadlock, and node03 parked with byteme3.
    The rest are defined in Proxmox but stopped.</p>
    <div class="table-scroll"><table>
      <thead><tr><th>Name</th><th>Type</th><th>Host</th><th>State</th><th>Role</th><th>Network</th><th>RAM</th><th>Disk</th><th>Tags</th></tr></thead>
      <tbody>{guest_rows()}</tbody>
    </table></div>
    <div class="parked">{parked_html()}</div>
  </section>

  <section class="band" id="changes">
    <div class="eyebrow">08 · Log</div>
    <h2>Recent changes</h2>
    <ol class="log">{log_html}</ol>
  </section>
</main>
<footer><div class="wrap">Built from live reads of the two running Proxmox hosts, Slurm, the UPS dashboard and
ups-guardian on {SNAPSHOT}. The Cloudflare and Tailscale parts were last read on {EDGE_READ}. Addresses, port numbers,
software versions and admin hostnames are left out on purpose. The topology was made with AI assistance.</div></footer>
<script>{JS}</script>
"""


def page_artifact(b):
    """The artifact host adds doctype, charset and viewport, so this starts at <title>."""
    return f"<title>{TITLE}</title>\n{FONTS}\n<style>{CSS}{PAGE_CSS}</style>\n{b}"


def page_site(b):
    """A complete document for nbdevlab.com."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{TITLE}</title>
<meta name="description" content="{esc(DESCRIPTION)}">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#000000">
<meta property="og:type" content="website">
<meta property="og:title" content="{TITLE}">
<meta property="og:description" content="{esc(DESCRIPTION)}">
{FONTS}
<style>{CSS}{PAGE_CSS}</style>
</head>
<body>
{b}
</body>
</html>
"""


def poster_page(svg, title):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)}</title>{FONTS}
<style>{CSS} body {{ margin: 0; }} .pz {{ width: auto; }}</style></head>
<body>{svg}</body></html>"""


def leak_check(name, doc):
    """Refuse to write a public file that carries anything from LEAK_PATTERNS. Only what a visitor can read
    is checked (text and attribute values), not the CSS or the script."""
    visible = re.sub(r"<style>.*?</style>|<script>.*?</script>|<link [^>]*>", " ", doc, flags=re.S)
    visible = re.sub(r'\sdata-(legs|x0|x1|t|c|speed|delay|rest|hold)="[^"]*"', " ", visible)  # animation geometry
    visible = re.sub(r'\s(x|y|x1|x2|y1|y2|cx|cy|r|rx|width|height|viewBox|d|transform|style|data-w)="[^"]*"',
                     " ", visible)
    hits = []
    for pat, what in LEAK_PATTERNS:
        for m in re.finditer(pat, visible, flags=re.I):
            ctx = visible[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
            hits.append(f"  {what}: {m.group(0)!r} in …{ctx}…")
    if hits:
        sys.exit(f"leak_check: {name} not written, it would publish:\n" + "\n".join(hits))


def write(path, doc):
    leak_check(path.name, doc)
    path.parent.mkdir(exist_ok=True)
    path.write_text(doc)


def main():
    p1, pw, p2, p3, fe = poster_network(), poster_workloads(), poster_slerm(), poster_power(), figure_edge()
    b = body(p1.render(), pw.render(), p2.render(), p3.render(), fe.render())
    write(OUT / "homelab-map.html", page_artifact(b))
    write(OUT / "site" / "nbdevlab-homelab.html", page_site(b))
    for name, s, title in (("network", p1, "nbdevlab homelab map"), ("workloads", pw, "slerm workloads"),
                           ("slerm", p2, "slerm LLM serving"),
                           ("power", p3, "power failure"), ("edge", fe, "public edge")):
        write(OUT / f"poster-{name}.html", poster_page(s.render(), title))
        print(f"poster-{name}.html  {s.w}x{s.h:g}")


if __name__ == "__main__":
    main()
