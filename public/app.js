// People Power frontend — homepage
const API_URL = window.PEOPLEPOWER_API_URL || "/api/episodes";

const audio = document.getElementById("audio");
const playerBtn = document.getElementById("player-btn");
const playerTitle = document.getElementById("player-title");
const playerMeta = document.getElementById("player-meta");
const grid = document.getElementById("episode-grid");

let currentEpisode = null;
let imageData = {};
let customImages = {};
let categoryData = {};
let customCategories = {};

const defaultArt = "https://app.springcast.fm/storage/artwork/6377/17987/oDhDgpiQ7VVby0y9Cf7FZ7mnzNid492nygTLDxy6.png";
const playIcon = '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
const pauseIcon = '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>';

function escapeHtml(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function getBestImage(ep) {
  if (ep.number && customImages[ep.number]) return customImages[ep.number];
  if (ep.number && imageData.byNumber && imageData.byNumber[ep.number]) return imageData.byNumber[ep.number];
  if (imageData.byTitle) {
    const norm = ep.title.toLowerCase().replace(/\s+/g, " ").trim();
    if (imageData.byTitle[norm]) return imageData.byTitle[norm];
  }
  if (ep.imageUrl) return ep.imageUrl;
  return defaultArt;
}

function getCatsForEpisode(ep) {
  if (ep.number && customCategories[ep.number]) return customCategories[ep.number];
  if (ep.number && categoryData.byNumber && categoryData.byNumber[ep.number]) return categoryData.byNumber[ep.number];
  if (categoryData.byTitle) {
    const norm = ep.title.toLowerCase().replace(/\s+/g, " ").trim();
    if (categoryData.byTitle[norm]) return categoryData.byTitle[norm];
  }
  return [];
}

function catSlugToName(slug) {
  const cats = categoryData.categories || [];
  const c = cats.find(x => x.slug === slug);
  return c ? c.name : slug;
}

function setPlayer(episode) {
  currentEpisode = episode;
  playerTitle.textContent = episode.number ? `#${episode.number} ${episode.title}` : episode.title;
  playerMeta.textContent = [episode.duration, episode.pubDateFormatted].filter(Boolean).join(" \u00b7 ");
  audio.src = episode.audioUrl;
}

function play(episode) {
  if (currentEpisode?.id !== episode.id) setPlayer(episode);
  audio.play();
}

playerBtn.addEventListener("click", () => {
  if (!currentEpisode) return;
  if (audio.paused) audio.play(); else audio.pause();
});
audio.addEventListener("play", () => { playerBtn.innerHTML = pauseIcon; });
audio.addEventListener("pause", () => { playerBtn.innerHTML = playIcon; });

function renderEpisodes(episodes) {
  if (!episodes.length) {
    grid.innerHTML = '<div class="episode-loading">Geen afleveringen gevonden.</div>';
    return;
  }

  grid.innerHTML = episodes.slice(0, 6).map((ep, i) => {
    const art = escapeHtml(getBestImage(ep));
    const cats = getCatsForEpisode(ep);
    const catHtml = cats.map(s => '<span class="ep-cat-tag">' + escapeHtml(catSlugToName(s)) + '</span>').join("");
    return '<article class="ep-row" data-idx="' + i + '">' +
      '<div class="ep-row-art">' +
        '<img src="' + art + '" alt="" loading="lazy" />' +
        '<button class="ep-row-play" data-idx="' + i + '" aria-label="Speel af">' +
          '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>' +
        '</button>' +
      '</div>' +
      '<div class="ep-row-body">' +
        '<div class="ep-row-num">' + (ep.number ? "#" + ep.number : "") + ' \u00b7 ' + (ep.pubDateFormatted || "") + '</div>' +
        '<h3 class="ep-row-title">' + escapeHtml(ep.title) + '</h3>' +
        '<p class="ep-row-desc">' + escapeHtml(ep.description) + '</p>' +
        '<div class="ep-row-bottom">' +
          '<span class="ep-row-meta">' + (ep.duration || "") + '</span>' +
          '<span class="ep-row-cats">' + catHtml + '</span>' +
        '</div>' +
      '</div>' +
    '</article>';
  }).join("");

  grid.querySelectorAll(".ep-row-play").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const idx = parseInt(btn.dataset.idx, 10);
      play(episodes[idx]);
      window.scrollTo({ top: document.getElementById("player").offsetTop - 80, behavior: "smooth" });
    });
  });

  grid.querySelectorAll(".ep-row").forEach(card => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".ep-row-play")) return;
      const idx = parseInt(card.dataset.idx, 10);
      const ep = episodes[idx];
      window.location.href = "/aflevering.html?idx=" + idx + "&id=" + encodeURIComponent(ep.id);
    });
  });
}

async function loadEpisodes() {
  try {
    const [res, imgRes, cusRes, catRes, cusCatRes] = await Promise.all([
      fetch(API_URL),
      fetch("/episode-images.json").catch(() => null),
      fetch("/episode-images-custom.json").catch(() => null),
      fetch("/episode-categories.json").catch(() => null),
      fetch("/episode-categories-custom.json").catch(() => null),
    ]);
    if (!res.ok) throw new Error("Kon afleveringen niet laden");
    const data = await res.json();
    const episodes = data.episodes || [];
    if (imgRes && imgRes.ok) imageData = await imgRes.json();
    if (cusRes && cusRes.ok) customImages = await cusRes.json();
    if (catRes && catRes.ok) categoryData = await catRes.json();
    if (cusCatRes && cusCatRes.ok) customCategories = await cusCatRes.json();
    if (episodes.length > 0) {
      setPlayer(episodes[0]);
      renderEpisodes(episodes);
    }
  } catch (err) {
    grid.innerHTML = `<div class="episode-loading">Fout bij laden: ${escapeHtml(err.message)}</div>`;
    playerTitle.textContent = "Geen aflevering geladen";
  }
}

loadEpisodes();
