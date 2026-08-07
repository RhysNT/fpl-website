// Shared nav bar. Every page includes <nav id="site-nav"></nav> in the header
// and <script src="nav.js"></script> before the closing body tag (or in head
// with defer). This keeps the link list in one place instead of duplicated
// across every HTML file.

const NAV_LINKS = [
  { href: "index.html", label: "Player Stats" },
  { href: "price_changes.html", label: "Price Changes" },
  { href: "fixtures.html", label: "Fixtures" },
  { href: "my_team.html", label: "Team Builder" },
  { href: "compare.html", label: "Compare" },
  { href: "weekly_picks.html", label: "Weekly Picks" },
  { href: "defcon.html", label: "DEFCON" },
  { href: "injuries.html", label: "Injuries" },
  { href: "chips.html", label: "Chips" },
];

function renderNav() {
  const nav = document.getElementById("site-nav");
  if (!nav) return;
  const currentPage = window.location.pathname.split("/").pop() || "index.html";
  nav.innerHTML = NAV_LINKS.map(link =>
    `<a href="${link.href}" class="${link.href === currentPage ? "active" : ""}">${link.label}</a>`
  ).join("");
}

renderNav();
