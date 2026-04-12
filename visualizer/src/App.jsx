import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import * as THREE from 'three';
import { Search, Network, X, Sparkles, Activity } from 'lucide-react';
import { UnrealBloomPass } from 'three-stdlib';
import './App.css';

// Node color palette for glassmorphism style
const COLORS = {
  entity: '#38bdf8', // Light blue
  concept: '#c084fc', // Purple
  ghost: '#94a3b8',   // Slate
  highlight: '#fcd34d' // Amber for selected/searched
};

function App() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNode, setSelectedNode] = useState(null);
  const [hoverNode, setHoverNode] = useState(null);
  const [bloomEnabled, setBloomEnabled] = useState(false);

  const fgRef = useRef();

  // Load data
  useEffect(() => {
    fetch('/latent_space.json')
      .then(res => res.json())
      .then(data => {
        // Ensure data formatting
        const nodes = data.nodes || [];
        const links = data.links || [];

        // Calculate degree for each node for initial sizing
        nodes.forEach(node => {
          node.degree = links.filter(l => l.source === node.id || l.target === node.id).length;
        });

        setGraphData({ nodes, links });
      })
      .catch(err => console.error("Failed to load latent_space.json:", err));
  }, []);

  // Set up Bloom Pass post-processing when the graph loads or bloom setting changes
  useEffect(() => {
    if (!fgRef.current) return;

    // Cleanup previous passes if any
    const composer = fgRef.current.postProcessingComposer();
    if (!composer) return;

    // Remove existing bloom passes
    composer.passes = composer.passes.filter(p => !(p instanceof UnrealBloomPass));

    if (bloomEnabled) {
      const resolution = new THREE.Vector2(window.innerWidth, window.innerHeight);
      const bloomPass = new UnrealBloomPass(resolution);
      bloomPass.strength = 1.5;
      bloomPass.radius = 0.4;
      bloomPass.threshold = 0.1;
      composer.addPass(bloomPass);
    }
  }, [bloomEnabled, graphData]);

  // Derived state for highlighting
  const { filteredNodes, highlightNodes, highlightLinks } = useMemo(() => {
    const nodes = new Set();
    const links = new Set();
    const fNodes = [];

    // Filter nodes by search query
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      graphData.nodes.forEach(node => {
        if (node.id.toLowerCase().includes(q)) {
          fNodes.push(node);
          nodes.add(node.id);
        }
      });
    }

    // Highlight logic based on selection or hover
    const activeNode = selectedNode || hoverNode;
    if (activeNode) {
      nodes.add(activeNode.id);
      graphData.links.forEach(link => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
        const targetId = typeof link.target === 'object' ? link.target.id : link.target;

        if (sourceId === activeNode.id || targetId === activeNode.id) {
          links.add(link);
          nodes.add(sourceId);
          nodes.add(targetId);
        }
      });
    }

    return { filteredNodes: fNodes, highlightNodes: nodes, highlightLinks: links };
  }, [graphData, searchQuery, selectedNode, hoverNode]);

  // Handlers
  const handleNodeClick = useCallback(node => {
    setSelectedNode(node);

    // Camera animation to focus node
    if (fgRef.current) {
      const distance = 40;
      const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);
      fgRef.current.cameraPosition(
        { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
        node,
        2000
      );
    }
  }, []);

  const handleConnectionClick = useCallback(nodeId => {
    const node = graphData.nodes.find(n => n.id === nodeId);
    if (node) {
      handleNodeClick(node);
    }
  }, [graphData, handleNodeClick]);

  // Visual logic
  const getNodeColor = useCallback(node => {
    if (highlightNodes.size > 0 && !highlightNodes.has(node.id)) {
      return '#222222'; // Dimmed (avoid rgba for ThreeJS color)
    }

    if (searchQuery && filteredNodes.some(n => n.id === node.id)) {
      return COLORS.highlight;
    }

    return COLORS[node.group] || COLORS.ghost;
  }, [highlightNodes, searchQuery, filteredNodes]);

  return (
    <div className="app-container">
      {/* HEADER PANEL - Glassmorphism */}
      <div className="header-panel glass-panel">
        <div className="header-title">
          <Activity size={24} color={COLORS.entity} />
          DAEMON.MD
        </div>
        <div className="header-stats">
          {graphData.nodes.length} Nodes • {graphData.links.length} Edges
        </div>

        <div className="search-container">
          <Search className="search-icon" size={16} />
          <input
            type="text"
            className="search-input"
            placeholder="Search latent space..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="legend-container">
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: COLORS.entity }}></div>
            <span>Entity</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: COLORS.concept }}></div>
            <span>Concept</span>
          </div>
          <div className="legend-item">
            <div className="legend-color" style={{ backgroundColor: COLORS.ghost }}></div>
            <span>Ghost (Unresolved)</span>
          </div>
        </div>
      </div>

      {/* CONTROLS PANEL */}
      <div className="controls-panel glass-panel">
        <label className="control-label">
          <Sparkles size={16} color={bloomEnabled ? '#fcd34d' : '#94a3b8'} />
          Bloom Effects
          <div className="toggle-switch">
            <input
              type="checkbox"
              checked={bloomEnabled}
              onChange={() => setBloomEnabled(!bloomEnabled)}
            />
            <span className="slider"></span>
          </div>
        </label>
      </div>

      {/* SIDE PANEL (NODE DETAILS) */}
      <div className={`node-panel glass-panel ${!selectedNode ? 'hidden' : ''}`}>
        {selectedNode && (
          <>
            <div className="node-panel-header">
              <div>
                <h2 className="node-title">{selectedNode.id}</h2>
                <span className="node-badge" style={{
                  backgroundColor: `${COLORS[selectedNode.group] || COLORS.ghost}33`,
                  color: COLORS[selectedNode.group] || COLORS.ghost,
                  border: `1px solid ${COLORS[selectedNode.group] || COLORS.ghost}66`
                }}>
                  {selectedNode.group}
                </span>
              </div>
              <button className="close-btn" onClick={() => setSelectedNode(null)}>
                <X size={20} />
              </button>
            </div>

            {selectedNode.details && (
              <div className="node-section">
                <h3 className="section-title">Details</h3>
                <div className="node-details">
                  {selectedNode.details}
                </div>
              </div>
            )}

            <div className="node-section">
              <h3 className="section-title">Connections</h3>
              <div className="connections-list">
                {graphData.links
                  .filter(l => {
                    const srcId = typeof l.source === 'object' ? l.source.id : l.source;
                    const tgtId = typeof l.target === 'object' ? l.target.id : l.target;
                    return srcId === selectedNode.id || tgtId === selectedNode.id;
                  })
                  .map((link, i) => {
                    const srcId = typeof link.source === 'object' ? link.source.id : link.source;
                    const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
                    const isSource = srcId === selectedNode.id;
                    const connectedId = isSource ? tgtId : srcId;

                    return (
                      <div
                        key={i}
                        className="connection-item"
                        onClick={() => handleConnectionClick(connectedId)}
                      >
                        <Network size={16} className="connection-icon" />
                        <span className="connection-name">{connectedId}</span>
                      </div>
                    );
                  })}
              </div>
            </div>
          </>
        )}
      </div>

      {/* 3D GRAPH */}
      <ForceGraph3D
        ref={fgRef}
        graphData={graphData}
        backgroundColor="rgba(0,0,0,0)" // Transparent to show CSS gradient
        showNavInfo={false}

        // Node styling
        nodeColor={getNodeColor}
        nodeOpacity={0.9} // nodeOpacity must be a Number, not a function
        nodeResolution={24} // Higher res for smoother spheres
        nodeVal={node => {
          const degree = node.degree || 1;
          return node.group === 'ghost' ? 1.5 : Math.max(3, Math.sqrt(degree) * 2);
        }}

        // Custom 3D Object for selected node aura
        nodeThreeObjectExtend={true}
        nodeThreeObject={node => {
          if (node.id === selectedNode?.id) {
            const size = node.group === 'ghost' ? 1.5 : Math.max(3, Math.sqrt(node.degree || 1) * 2);
            // Create a wireframe aura around selected node
            const geometry = new THREE.SphereGeometry(size * 1.4, 16, 16);
            const material = new THREE.MeshBasicMaterial({
              color: COLORS.highlight,
              wireframe: true,
              transparent: true,
              opacity: 0.3
            });
            return new THREE.Mesh(geometry, material);
          }
          return null;
        }}

        // Link styling
        linkOpacity={0.3}
        linkColor={link => {
          if (highlightLinks.has(link)) return '#ffffff';
          return 'rgba(255,255,255,0.1)';
        }}
        linkWidth={link => highlightLinks.has(link) ? 1.5 : 0.5}

        // Interaction
        onNodeClick={handleNodeClick}
        onNodeHover={node => setHoverNode(node)}

        // Custom Tooltip HTML
        nodeLabel={node => {
          return `
            <div class="graph-tooltip">
              <div style="font-weight: bold; margin-bottom: 2px;">${node.id}</div>
              <div style="font-size: 11px; opacity: 0.7; text-transform: uppercase;">${node.group}</div>
            </div>
          `;
        }}
      />
    </div>
  );
}

export default App;
