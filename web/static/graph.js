// Encyclist graph explorer — D3 force-directed layout.
// Lazy: fetches /graph/data with the seed entity (or sample if none) and
// renders nodes + edges. Clicking a node navigates to its detail page.

(function () {
    "use strict";

    function buildDataURL() {
        const params = new URLSearchParams();
        if (window.GRAPH_SEED_ENTITY) params.set("entity_id", window.GRAPH_SEED_ENTITY);
        if (window.GRAPH_SEED_TYPE) params.set("type", window.GRAPH_SEED_TYPE);
        const qs = params.toString();
        return "/graph/data" + (qs ? "?" + qs : "");
    }

    function nodeURL(n) {
        if (n.kind === "entity") return "/entity/" + n.id;
        if (n.kind === "doc") return "/doc/" + n.id;
        return null;
    }

    function init() {
        if (typeof d3 === "undefined") {
            console.error("[graph] D3 not loaded yet, retrying...");
            setTimeout(init, 100);
            return;
        }

        const svgEl = document.getElementById("graph-svg");
        const emptyEl = document.getElementById("graph-empty");
        if (!svgEl) return;

        fetch(buildDataURL())
            .then((r) => r.json())
            .then((data) => render(data, svgEl, emptyEl))
            .catch((err) => {
                console.error("[graph] failed to load data", err);
                if (emptyEl) {
                    emptyEl.hidden = false;
                    emptyEl.textContent = "Failed to load graph data: " + err.message;
                }
            });
    }

    function render(data, svgEl, emptyEl) {
        const nodes = data.nodes || [];
        const edges = (data.edges || []).map((e) => Object.assign({}, e));

        if (!nodes.length) {
            if (emptyEl) emptyEl.hidden = false;
            return;
        }

        const width = svgEl.clientWidth || 800;
        const height = parseInt(svgEl.getAttribute("height"), 10) || 600;

        const svg = d3.select(svgEl);
        svg.selectAll("*").remove();
        svg.attr("viewBox", `0 0 ${width} ${height}`);

        const container = svg.append("g");

        const zoom = d3.zoom()
            .scaleExtent([0.2, 4])
            .on("zoom", (event) => container.attr("transform", event.transform));
        svg.call(zoom);

        const link = container.append("g")
            .attr("class", "graph-links")
            .selectAll("line")
            .data(edges)
            .enter().append("line")
            .attr("class", "graph-link")
            .attr("stroke-width", 1.2);

        const linkLabel = container.append("g")
            .attr("class", "graph-link-labels")
            .selectAll("text")
            .data(edges)
            .enter().append("text")
            .attr("class", "graph-link-label")
            .text((d) => d.label || "");

        const node = container.append("g")
            .attr("class", "graph-nodes")
            .selectAll("g")
            .data(nodes, (d) => d.id)
            .enter().append("g")
            .attr("class", (d) => "graph-node " + (d.kind || "unknown"));

        node.append("circle").attr("r", 10);
        node.append("title").text((d) => d.label + " (" + d.id + ")");
        node.append("text")
            .attr("x", 14)
            .attr("y", 4)
            .text((d) => (d.label && d.label.length > 28) ? d.label.slice(0, 27) + "…" : d.label);

        node.style("cursor", (d) => nodeURL(d) ? "pointer" : "default")
            .on("click", (event, d) => {
                const url = nodeURL(d);
                if (url) window.location.href = url;
            });

        const simulation = d3.forceSimulation(nodes)
            .force("link", d3.forceLink(edges).id((d) => d.id).distance(90))
            .force("charge", d3.forceManyBody().strength(-220))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collide", d3.forceCollide().radius(28))
            .on("tick", () => {
                link
                    .attr("x1", (d) => d.source.x)
                    .attr("y1", (d) => d.source.y)
                    .attr("x2", (d) => d.target.x)
                    .attr("y2", (d) => d.target.y);
                linkLabel
                    .attr("x", (d) => (d.source.x + d.target.x) / 2)
                    .attr("y", (d) => (d.source.y + d.target.y) / 2);
                node.attr("transform", (d) => `translate(${d.x}, ${d.y})`);
            });

        const drag = d3.drag()
            .on("start", (event, d) => {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x; d.fy = d.y;
            })
            .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
            .on("end", (event, d) => {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null; d.fy = null;
            });
        node.call(drag);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
