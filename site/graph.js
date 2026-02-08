// Data injected by template.html
const allNodes = window.GRAPH_NODES || [];
const allLinks = window.GRAPH_LINKS || [];

const nodeById = new Map(allNodes.map(n => [n.id, n]));

const svg = d3.select("svg");
const width = svg.node().clientWidth;
const height = svg.node().clientHeight;

const g = svg.append("g");

let link = g.append("g")
  .attr("stroke-width", 1)
  .selectAll("line");

let node = g.append("g")
  .attr("stroke-width", 1.5)
  .selectAll("g");

let currentCenterId = null;

const simulation = d3.forceSimulation()
  .force("link", d3.forceLink()
      .id(d => d.id)
      .distance(d => {
        if (d.relation === "acg-method") return 40;
        if (d.relation === "uses-acg") return 80;
        if (d.relation === "provides") return 80;
        if (d.relation === "owns-name") return 60;
        if (d.relation === "can-call") return 70;
        return 60;
      })
      .strength(0.4)
  )
  .force("charge", d3.forceManyBody().strength(-80))
  .force("center", d3.forceCenter(width / 2, height / 2))
  .force("collision", d3.forceCollide().radius(d => {
    if (d.type === "binary") return 28;
    if (d.type === "service") return 24;
    if (d.type === "acg") return 20;
    return 14;
  }));

simulation.on("tick", () => {
  link
    .attr("x1", d => d.source.x)
    .attr("y1", d => d.source.y)
    .attr("x2", d => d.target.x)
    .attr("y2", d => d.target.y);

  node
    .attr("transform", d => `translate(${d.x},${d.y})`);
});

svg.call(
  d3.zoom()
    .scaleExtent([0.2, 4])
    .on("zoom", (event) => {
      g.attr("transform", event.transform);
    })
);

function drag(simulation) {
  function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }

  function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }

  function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }

  return d3.drag()
    .on("start", dragstarted)
    .on("drag", dragged)
    .on("end", dragended);
}

const details = document.getElementById("details");

// Core render: no history / URL changes here.
function focusNode(centerId) {
  const center = nodeById.get(centerId);
  if (!center) return;
  currentCenterId = centerId;

  const nodeIds = new Set([centerId]);
  const subLinks = [];

  allLinks.forEach(l => {
    if (l.source === centerId || l.target === centerId) {
      subLinks.push(Object.assign({}, l));
      nodeIds.add(l.source);
      nodeIds.add(l.target);
    }
  });

  const subNodes = Array.from(nodeIds).map(id => {
    const base = nodeById.get(id);
    return Object.assign({}, base);
  });

  simulation.nodes(subNodes);
  simulation.force("link").links(subLinks);

  link = link.data(subLinks, d => d.source + "->" + d.target);
  link.exit().remove();
  const linkEnter = link.enter().append("line")
    .attr("class", d => "link " + (d.relation || ""));
  link = linkEnter.merge(link);

  node = node.data(subNodes, d => d.id);
  node.exit().remove();
  const nodeEnter = node.enter().append("g")
    .attr("class", d => "node " + d.type)
    .call(drag(simulation));

  nodeEnter.append("circle")
    .attr("r", d => {
      if (d.type === "binary") return 8;
      if (d.type === "service") return 7;
      if (d.type === "acg") return 6;
      return 4;
    });

  nodeEnter.append("text")
    .attr("x", 9)
    .attr("y", 3)
    .text(d => d.label);

  nodeEnter.on("click", (event, d) => {
    event.preventDefault();
    selectNode(d.id);
  });

  node = nodeEnter.merge(node);

  simulation.alpha(1).restart();
  updateDetails(center);
}

// Selection API: only manipulates hash.
// History/back is driven by the browser's hash history.
function selectNode(id) {
  if (!id) return;
  const newHash = "#" + encodeURIComponent(id);
  if (location.hash === newHash) {
    // hash unchanged: just render
    focusNode(id);
  } else {
    // changing hash will create a history entry and fire hashchange
    location.hash = newHash;
  }
}

function updateDetails(d) {
  node.classed("selected", n => n.id === d.id);

  const neighbors = new Set();
  const outgoingCanCallIds = new Set();
  const incomingCanCallIds = new Set();

  simulation.force("link").links().forEach(l => {
    const sid = typeof l.source === "object" ? l.source.id : l.source;
    const tid = typeof l.target === "object" ? l.target.id : l.target;

    if (sid === d.id || tid === d.id) {
      neighbors.add(sid);
      neighbors.add(tid);
    }
    if (l.relation === "can-call") {
      if (sid === d.id) outgoingCanCallIds.add(tid);
      if (tid === d.id) incomingCanCallIds.add(sid);
    }
  });
  neighbors.delete(d.id);

  const neighborNodes = Array.from(neighbors).map(id =>
    simulation.nodes().find(n => n.id === id)
  ).filter(Boolean);

  let html = "";
  html += `<h3>${escapeHtml(d.label)} <small>[${escapeHtml(d.type)}]</small></h3>`;
  html += "<pre style='white-space:pre-wrap; font-size:11px;'>";
  html += escapeHtml(JSON.stringify(stripInternal(d), null, 2));
  html += "</pre>";

  if (neighborNodes.length) {
    const binaries  = neighborNodes.filter(n => n.type === "binary");
    const services  = neighborNodes.filter(n => n.type === "service");
    const acgs      = neighborNodes.filter(n => n.type === "acg");
    const endpoints = neighborNodes.filter(n => n.type === "endpoint");

    if (binaries.length) {
      html += "<h4>Underlying binaries</h4><ul>";
      binaries.forEach(b => {
        const path = b.binaryPath || "";
        const extra = path ? ` (${escapeHtml(path)})` : "";
        html += `<li><a href="#" data-id="${escapeAttr(b.id)}">${escapeHtml(b.label)}${extra}</a></li>`;
      });
      html += "</ul>";
    }

    let outboundIds = new Set();
    let inboundIds = new Set();
    let outboundNodes = [];
    let inboundNodes = [];

    if (d.type === "service") {
      outboundNodes = Array.from(outgoingCanCallIds).map(id =>
        simulation.nodes().find(n => n.id === id)
      ).filter(Boolean).filter(n => n.type === "service");

      inboundNodes = Array.from(incomingCanCallIds).map(id =>
        simulation.nodes().find(n => n.id === id)
      ).filter(Boolean).filter(n => n.type === "service");

      outboundIds = new Set(outboundNodes.map(s => s.id));
      inboundIds = new Set(inboundNodes.map(s => s.id));

      if (outboundNodes.length || d.outboundAll) {
        html += "<h4>Outbound allowed services (roles.d permissions)</h4><ul>";
        outboundNodes.forEach(s => {
          html += `<li><a href="#" data-id="${escapeAttr(s.id)}">${escapeHtml(s.label)}</a></li>`;
        });
        if (d.outboundAll) {
          html += "<li><em>ALL services (*)</em></li>";
        }
        html += "</ul>";
      }

      if (inboundNodes.length) {
        html += "<h4>Explicit inbound callers (from roles.d)</h4><ul>";
        inboundNodes.forEach(s => {
          html += `<li><a href="#" data-id="${escapeAttr(s.id)}">${escapeHtml(s.label)}</a></li>`;
        });
        html += "</ul>";
      }
    }

    const otherServiceNeighbors = services.filter(s =>
      !outboundIds.has(s.id) && !inboundIds.has(s.id)
    );

    if (otherServiceNeighbors.length) {
      html += "<h4>Other neighbor services</h4><ul>";
      otherServiceNeighbors.forEach(s => {
        const bin = s.binaryPath || s.binary || s.execCommand || s.exec || s.exe || "";
        const extra = bin ? ` [binary: ${escapeHtml(bin)}]` : "";
        html += `<li><a href="#" data-id="${escapeAttr(s.id)}">${escapeHtml(s.label)}${extra}</a></li>`;
      });
      html += "</ul>";
    }

    if (endpoints.length) {
      html += "<h4>Endpoints</h4><ul>";
      endpoints.forEach(ep => {
        const svc = ep.serviceName ? ` [${escapeHtml(ep.serviceName)}]` : "";
        html += `<li><a href="#" data-id="${escapeAttr(ep.id)}">${escapeHtml(ep.label)}${svc}</a></li>`;
      });
      html += "</ul>";
    }

    if (acgs.length) {
      html += "<h4>ACGs</h4><ul>";
      acgs.forEach(a => {
        html += `<li><a href="#" data-id="${escapeAttr(a.id)}">${escapeHtml(a.label)}</a></li>`;
      });
      html += "</ul>";
    }
  }

  details.innerHTML = html;

  details.querySelectorAll("a[data-id]").forEach(a => {
    a.addEventListener("click", e => {
      e.preventDefault();
      const id = a.getAttribute("data-id");
      selectNode(id);
    });
  });
}

function stripInternal(d) {
  const copy = {};
  for (const k in d) {
    if (k === "index" || k === "vx" || k === "vy" ||
        k === "x" || k === "y" || k === "fx" || k === "fy") continue;
    copy[k] = d[k];
  }
  return copy;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeAttr(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

const searchInput = document.getElementById("search");
const searchKind = document.getElementById("search-kind");
const searchBtn = document.getElementById("search-btn");
const resultsDiv = document.getElementById("results");

searchBtn.addEventListener("click", runSearch);
searchInput.addEventListener("keydown", e => {
  if (e.key === "Enter") runSearch();
});

function runSearch() {
  const q = searchInput.value.trim().toLowerCase();
  const kind = searchKind.value;
  resultsDiv.innerHTML = "";
  if (!q) return;

  const matches = allNodes.filter(n => {
    if (kind !== "any" && n.type !== kind) return false;
    return (
      (n.label && n.label.toLowerCase().includes(q)) ||
      (String(n.id).toLowerCase().includes(q)) ||
      (n.binaryPath && String(n.binaryPath).toLowerCase().includes(q))
    );
  }).slice(0, 80);

  if (!matches.length) {
    resultsDiv.innerHTML = "<p>No matches</p>";
    return;
  }

  let html = "<ul>";
  matches.forEach(m => {
    html += `<li><a href="#" data-id="${escapeAttr(m.id)}">${escapeHtml(m.label)} <small>[${escapeHtml(m.type)}]</small></a></li>`;
  });
  html += "</ul>";
  resultsDiv.innerHTML = html;

  resultsDiv.querySelectorAll("a").forEach(a => {
    a.addEventListener("click", e => {
      e.preventDefault();
      const id = a.getAttribute("data-id");
      selectNode(id);
    });
  });
}

// React to Back/Forward (hash changes)
window.addEventListener("hashchange", () => {
  const h = location.hash;
  if (!h) return;
  const id = decodeURIComponent(h.slice(1));
  if (!id || id === currentCenterId) return;
  focusNode(id);
});

// Initial selection
(function init() {
  let startId = null;

  if (location.hash) {
    startId = decodeURIComponent(location.hash.slice(1));
  } else {
    const defaultNode =
      allNodes.find(n => n.type === "acg") ||
      allNodes.find(n => n.type === "service") ||
      allNodes.find(n => n.type === "binary") ||
      allNodes[0];

    if (defaultNode) {
      startId = defaultNode.id;
    }
  }

  if (!startId) return;

  // set hash so first selection is also in history
  const newHash = "#" + encodeURIComponent(startId);
  if (location.hash !== newHash) {
    location.hash = newHash;
    // focusNode will run via hashchange
  } else {
    focusNode(startId);
  }
})();
