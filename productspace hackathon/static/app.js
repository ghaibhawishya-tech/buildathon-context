const $ = (id) => document.getElementById(id);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const stamp = (n) =>
  Math.floor(n / 60) + ":" + String(Math.floor(n % 60)).padStart(2, "0");
const pages = {
  studio: "Clip studio",
  calendar: "Content calendar",
  memory: "Brand memory",
};
let state,
  project,
  page = "studio",
  filter = "All arcs",
  current,
  platform = "YouTube",
  timer;
async function api(url, body) {
  const form = body instanceof FormData;
  const res = await fetch(
    url,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: form ? {} : { "Content-Type": "application/json" },
          body: form ? body : JSON.stringify(body),
        },
  );
  const data = await res
    .json()
    .catch(() => ({ error: "Request failed (" + res.status + ")." }));
  if (!res.ok) throw Error(data.error || "Request failed.");
  return data;
}
function message(text) {
  const notice = document.querySelector("dialog[open] .notice");
  if (notice) {
    notice.textContent = text;
    return;
  }
  const toast = $("toast");
  toast.textContent = text;
  toast.style.display = "block";
  clearTimeout(timer);
  timer = setTimeout(() => (toast.style.display = "none"), 4000);
}
function bind(id, fn) {
  const el = $(id);
  if (el)
    el.onclick = async () => {
      el.disabled = true;
      try {
        await fn();
      } catch (e) {
        message(e.message);
      } finally {
        el.disabled = false;
      }
    };
}
const url = (tail = "") => "/api/projects/" + project.id + tail;
const cuturl = (tail) => url("/" + current.id + tail);
let activeRefresh = 0,
  progressTimer;
async function refresh(id) {
  const version = ++activeRefresh;
  clearTimeout(progressTimer);
  state = await api("/api/studio");
  let pid = id || project?.id || state.projects[0]?.id;
  if (!pid) {
    pid = (await api("/api/demo", {})).id;
    state = await api("/api/studio");
  }
  const updated = await api("/api/projects/" + pid);
  if (version !== activeRefresh) return;
  project = updated;
  paint();
  if (
    /^(Reading source|Transcribing|Finding emotional arcs)/.test(project.status)
  ) {
    progressTimer = setTimeout(
      () => refresh(pid).catch((e) => message(e.message)),
      1400,
    );
  }
}
function bars(c) {
  const values = c.waveform?.length
    ? c.waveform
    : c.curve.map((v) => -40 + v * 4);
  return values
    .map(
      (v) =>
        '<span style="height:' +
        Math.round(4 + Math.max(0, Math.min(1, (v + 55) / 50)) * 46) +
        'px"></span>',
    )
    .join("");
}
function paint() {
  $("crumb").textContent = pages[page];
  document
    .querySelectorAll("nav button")
    .forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  const header =
    '<div class="heading"><div><small class="eyebrow">AFTERTONE / WORKSPACE</small><h1>' +
    pages[page] +
    "</h1></div>";
  if (page === "memory") {
    const metrics = state.metrics;
    $("main").innerHTML =
      header +
      '</div><div class="grid"><section class="panel"><div class="tag">Creator edits</div><div class="stat">' +
      state.edits +
      '</div><h2>Voice memory</h2><p>Saved edits teach the studio your typical copy length, casing and hashtag use for each platform.</p></section><section class="panel"><div class="tag">Reported results</div><div class="stat">' +
      metrics.length +
      "</div><h2>Retention signals</h2><p>Record average percentage viewed in a moment’s review. Future cuts with similar emotional arcs inherit that signal.</p></section></div>" +
      (state.examples || [])
        .map(
          (e) =>
            '<section class="panel"><div class="tag">' +
            esc(e.platform) +
            " · saved voice edit</div><p><del>" +
            esc(e.before) +
            "</del></p><strong>" +
            esc(e.after) +
            "</strong></section>",
        )
        .join("") +
      metrics
        .map(
          (m) =>
            '<div class="panel line"><strong>' +
            esc(m.arc) +
            "</strong><span>" +
            m.retention +
            "% average viewed</span></div>",
        )
        .join("");
    return;
  }
  if (page === "calendar") {
    $("main").innerHTML =
      header +
      '</div><p class="sub">Editorial plans and approved YouTube uploads, in your local time zone.</p>' +
      (state.calendar.length
        ? state.calendar
            .map(
              (x) =>
                '<div class="panel"><div class="line"><div class="tag">' +
                esc(x.platform) +
                " · " +
                esc(new Date(x.at * 1000).toLocaleString()) +
                '</div><span class="status">' +
                esc(x.status) +
                "</span></div><h3>" +
                esc(x.copy) +
                "</h3><p>" +
                esc(x.title) +
                "</p>" +
                (["Planned", "Scheduled"].includes(x.status)
                  ? '<button class="outline" data-cancel="' +
                    esc(x.id) +
                    '">Cancel plan</button>'
                  : "") +
                "</div>",
            )
            .join("")
        : '<div class="empty">Your calendar is clear. Open a moment and choose a publishing time to add your first plan.</div>');
    return;
  }
  const options = state.projects
    .map(
      (p) =>
        '<option value="' +
        p.id +
        '" ' +
        (p.id === project.id ? "selected" : "") +
        ">" +
        esc(p.title) +
        "</option>",
    )
    .join("");
  const source = project.demo ? "ORIGINAL DEMO PODCAST" : "IMPORTED SOURCE";
  const subtitle = project.demo
    ? "An audio essay on the stories that survive the edit."
    : "Review the emotional turns in your recording.";
  const cards = project.clips.filter(
    (c) => filter === "All arcs" || filter === c.arc,
  );
  $("main").innerHTML =
    header +
    '<select id="projects" aria-label="Source recording">' +
    options +
    '</select></div><section class="hero"><div class="art"></div><div class="hero-inner"><span class="meta">' +
    source +
    "</span><h2>" +
    esc(project.title) +
    "</h2><p>" +
    subtitle +
    "</p>" +
    (project.status === "Ready"
      ? '<button class="play" id="listen">▶ &nbsp; Play source</button><div id="player"></div>'
      : "") +
    '</div></section><div class="listhead"><h2>Selected moments <span>' +
    project.clips.length +
    '</span></h2><select id="filter" aria-label="Filter emotional arcs">' +
    ["All arcs", ...new Set(project.clips.map((c) => c.arc))]
      .map(
        (x) =>
          "<option " +
          (filter === x ? "selected" : "") +
          ">" +
          esc(x) +
          "</option>",
      )
      .join("") +
    '</select></div><div class="cards">' +
    (cards
      .map(
        (c, i) =>
          '<article class="card"><div class="tile ' +
          ["", "teal", "lilac"][i % 3] +
          '" aria-hidden="true"><div class="wave">' +
          bars(c) +
          '</div></div><div><div class="tag">' +
          esc(c.arc) +
          "</div><h3>" +
          esc(c.title) +
          '</h3><div class="info">' +
          stamp(c.start) +
          " — " +
          stamp(c.end) +
          " &nbsp;·&nbsp; " +
          Math.round(c.end - c.start) +
          's</div></div><div class="cut"><div class="rating"><strong>' +
          c.score +
          '</strong><small>cut score</small></div><button class="action" data-cut="' +
          c.id +
          '" aria-label="Review moment ' +
          (i + 1) +
          '">↗</button></div></article>',
      )
      .join("") || '<div class="empty">' + esc(project.status) + "</div>") +
    "</div>" +
    (state.metrics.length
      ? '<div class="actions"><button class="outline" id="rerank">Re-rank using retention</button></div>'
      : "");
  $("projects").onchange = async (e) => {
    filter = "All arcs";
    await refresh(e.target.value);
  };
  $("filter").onchange = (e) => {
    filter = e.target.value;
    paint();
  };
  bind("listen", () => {
    $("listen").hidden = true;
    $("listen").style.display = "none";
    $("player").innerHTML =
      '<audio controls autoplay src="' + url("/source") + '"></audio>';
  });
  bind("rerank", async () => {
    await api(url("/rank"), {});
    filter = "All arcs";
    await refresh();
    message("Ranking updated using saved retention.");
  });
}
function review(id) {
  current = project.clips.find((c) => c.id === id);
  platform = "YouTube";
  const c = current;
  $("reviewbody").innerHTML =
    '<div class="line"><div><small class="eyebrow">' +
    esc(c.arc) +
    " · " +
    esc(c.editor || "Local signals") +
    " · " +
    stamp(c.start) +
    " — " +
    stamp(c.end) +
    '</small><h2>Moment review</h2></div><button class="close" aria-label="Close">×</button></div><div class="reviewgrid"><div><video id="preview" controls preload="metadata" poster="/static/cover.jpg"></video><div class="actions"><a id="mp4" class="primary" href="' +
    cuturl("/export/mp4?download=1") +
    '">↓ MP4</a><a id="srt" class="outline" href="' +
    cuturl("/export/srt") +
    '">↓ SRT</a></div><details><summary>Timed transcript</summary>' +
    c.rows
      .map(
        (r) =>
          '<div class="transcript"><time>' +
          stamp(r[0]) +
          "</time>" +
          esc(r[2]) +
          "</div>",
      )
      .join("") +
    '</details></div><div><span class="tag">Cut score · ' +
    c.score +
    "/100</span><h3>" +
    esc(c.title) +
    "</h3><ul>" +
    c.reasons.map((r) => "<li>" + esc(r) + "</li>").join("") +
    '</ul><div class="actions">' +
    Object.keys(c.copy)
      .sort((a, b) =>
        a === "YouTube" ? -1 : b === "YouTube" ? 1 : a.localeCompare(b),
      )
      .map(
        (p) =>
          '<button class="chip" data-platform="' + p + '">' + p + "</button>",
      )
      .join("") +
    '</div><label for="copy">Platform copy</label><textarea id="copy" maxlength="2000"></textarea><button class="outline" id="save">Save voice edit</button><details><summary>Plan publication</summary><label>Local date and time<input id="when" type="datetime-local"></label><div id="publishopts"></div><button class="primary" id="schedule">Add to calendar</button></details><details><summary>Record performance</summary><label>Average percentage viewed<input type="number" id="retention" min="0" max="100" placeholder="e.g. 72"></label><button class="outline" id="learn">Save retention</button></details><p class="notice" role="status"></p></div></div>';
  choosePlatform();
  bind("save", async () => {
    await api(cuturl("/edit"), { platform, copy: $("copy").value });
    current.copy[platform] = $("copy").value;
    await refresh();
    message("Edit saved to your brand memory.");
  });
  bind("learn", async () => {
    if ($("retention").value === "")
      throw Error("Enter the observed retention percentage.");
    await api(cuturl("/metric"), { retention: Number($("retention").value) });
    await refresh();
    message("Retention recorded for future rankings.");
  });
  bind("schedule", async () => {
    const at = new Date($("when").value).getTime() / 1000;
    if (!at) throw Error("Choose a date and time.");
    await api(cuturl("/schedule"), {
      platform,
      copy: $("copy").value,
      at,
      auto: $("auto")?.checked === true,
    });
    await refresh();
    message("Added to your content calendar.");
  });
  $("review").showModal();
}
function choosePlatform() {
  const media = cuturl("/export/mp4?platform=" + encodeURIComponent(platform));
  $("preview").src = media;
  $("mp4").href = media + "&download=1";
  $("srt").href = cuturl(
    "/export/srt?platform=" + encodeURIComponent(platform),
  );
  $("copy").value = current.copy[platform];
  document
    .querySelectorAll("[data-platform]")
    .forEach((b) =>
      b.classList.toggle("selected", platform === b.dataset.platform),
    );
  $("publishopts").innerHTML =
    platform === "YouTube"
      ? state.linked
        ? '<label class="checkbox"><input id="auto" type="checkbox"> Automatically upload publicly to my YouTube channel at this time</label>'
        : state.youtube
          ? '<p><a href="/youtube/connect"><u>Connect YouTube for optional automatic publishing</u></a></p>'
          : "<p>Calendar planning is available. Configure Google OAuth on your installation to enable YouTube publishing.</p>"
      : "<p>Calendar reminder for manual publishing.</p>";
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.classList.contains("close")) b.closest("dialog").close();
  if (b.dataset.page) {
    page = b.dataset.page;
    paint();
  }
  if (b.dataset.cut) review(b.dataset.cut);
  if (b.dataset.platform) {
    platform = b.dataset.platform;
    choosePlatform();
  }
  if (b.dataset.cancel) {
    try {
      await api("/api/calendar/" + b.dataset.cancel + "/cancel", {});
      await refresh();
    } catch (e) {
      message(e.message);
    }
  }
});
$("review").onclose = () => {
  $("reviewbody").innerHTML = "";
};
$("new").onclick = () => {
  $("cloudoption").style.display = state?.sarvam ? "flex" : "none";
  $("service").textContent = state?.sarvam
    ? "Offline transcription is available. Enable Sarvam below for optional cloud processing."
    : "Captions are optional. Offline speech recognition supports English and Hindi. Choose the spoken language below.";
  $("importer").showModal();
};
$("upload").onsubmit = async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector(".primary");
  btn.disabled = true;
  try {
    const data = new FormData(e.target);
    if (!data.get("srt")?.size) data.delete("srt");
    const { id } = await api("/api/import", data);
    $("importer").close();
    page = "studio";
    filter = "All arcs";
    await refresh(id);
  } catch (e) {
    $("service").textContent = e.message;
  } finally {
    btn.disabled = false;
  }
};
refresh().catch((e) => {
  $("main").textContent = e.message;
});
