/**
 * Shared Boardman top nav for static pages (arena / hub / docs).
 * Usage: include boardman-nav.css + this script; call BoardmanNav.mount()
 * or auto-mounts on DOMContentLoaded if #bm-nav-root or body[data-bm-nav] exists.
 */
(function () {
  var LINKS = [
    { href: "/", label: "Home", match: ["/", "/rematch", "/rematch/"] },
    { href: "/app", label: "Play", match: ["/app"] },
    { href: "/agentic/arena.html", label: "Arena", match: ["/agentic/arena"] },
    { href: "/metrics", label: "Metrics", match: ["/metrics", "/agentic/metrics"] },
    {
      href: "/agentic/football-managers.html",
      label: "AFM",
      match: ["/agentic/football-managers"],
    },
    { href: "/agentic/football-catalog.html", label: "Catalog", match: ["/agentic/football-catalog"] },
    { href: "/agentic/admin-dashboard.html", label: "Admin", match: ["/agentic/admin-dashboard"] },
    { href: "/agentic/hub.html", label: "Hub", match: ["/agentic/hub"] },
    { href: "/agentic/docs.html", label: "Docs", match: ["/agentic/docs"] },
    { href: "/leaderboard", label: "Board", match: ["/leaderboard"] },
    { href: "/get-usdc", label: "Fund", match: ["/get-usdc"] },
  ];

  var BOT =
    (typeof window !== "undefined" && window.BOARDMAN_BOT_URL) ||
    "https://t.me/myboardmanOfficialBot";

  function isActive(link, path) {
    var p = path || "";
    if (link.href === "/") {
      return p === "/" || p === "" || p === "/rematch" || p === "/rematch/";
    }
    return (link.match || [link.href]).some(function (m) {
      return p === m || p.indexOf(m) === 0;
    });
  }

  function render() {
    var path = (window.location && window.location.pathname) || "";
    var linksHtml = LINKS.map(function (l) {
      var active = isActive(l, path) ? " bm-nav-active" : "";
      return (
        '<a href="' +
        l.href +
        '" class="' +
        active.trim() +
        '">' +
        l.label +
        "</a>"
      );
    }).join("");

    return (
      '<header class="bm-nav" role="banner">' +
      '<div class="bm-nav-inner">' +
      '<a class="bm-nav-brand" href="/">' +
      '<img src="/boardman-logo.png" alt="" width="28" height="28" onerror="this.src=\'/boardman-logo.jpg\'" />' +
      '<span><span class="bm-accent">Board</span>man</span>' +
      "</a>" +
      '<nav class="bm-nav-links" aria-label="Boardman">' +
      linksHtml +
      "</nav>" +
      '<div class="bm-nav-actions">' +
      '<a class="bm-nav-bot" href="' +
      BOT +
      '" target="_blank" rel="noreferrer">Bot</a>' +
      '<a class="bm-nav-sq" href="https://playingsidequest.fun">sideQuest</a>' +
      "</div>" +
      "</div>" +
      "</header>"
    );
  }

  function mount(target) {
    var el =
      typeof target === "string"
        ? document.querySelector(target)
        : target || document.getElementById("bm-nav-root");
    if (el) {
      el.outerHTML = render();
      return;
    }
    if (document.body && document.body.getAttribute("data-bm-nav") !== null) {
      document.body.insertAdjacentHTML("afterbegin", render());
    }
  }

  window.BoardmanNav = { mount: mount, render: render, LINKS: LINKS };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      mount();
    });
  } else {
    mount();
  }
})();
