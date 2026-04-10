import React, { useState, useEffect, useRef } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import * as THREE from 'three';
import './App.css';

function App() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const fgRef = useRef();

  useEffect(() => {
    // Load the JSON data
    fetch('/latent_space.json')
      .then(res => res.json())
      .then(data => {
        setGraphData(data);
      })
      .catch(err => console.error("Failed to load latent_space.json:", err));
  }, []);

  return (
    <div style={{ margin: 0, padding: 0, overflow: 'hidden', backgroundColor: '#0a0a0a', height: '100vh', width: '100vw' }}>
      <div style={{
        position: 'absolute',
        top: 20,
        left: 20,
        color: '#00ff00',
        fontFamily: 'monospace',
        zIndex: 10,
        pointerEvents: 'none'
      }}>
        <h1 style={{ margin: 0, fontSize: '1.5rem' }}>DAEMON.MD // Latent Space Explorer</h1>
        <p style={{ margin: '5px 0 0 0', opacity: 0.7 }}>Nodes: {graphData.nodes.length} | Edges: {graphData.links.length}</p>

        <div style={{ marginTop: 20, fontSize: '0.9rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 5 }}>
            <div style={{ width: 12, height: 12, backgroundColor: '#00ffff', borderRadius: '50%', marginRight: 8 }}></div>
            <span>Entity</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 5 }}>
            <div style={{ width: 12, height: 12, backgroundColor: '#ff00ff', borderRadius: '50%', marginRight: 8 }}></div>
            <span>Concept</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <div style={{ width: 12, height: 12, backgroundColor: '#555555', borderRadius: '50%', marginRight: 8 }}></div>
            <span>Ghost (Unresolved)</span>
          </div>
        </div>
      </div>

      <ForceGraph3D
        ref={fgRef}
        graphData={graphData}
        backgroundColor="#0a0a0a"
        showNavInfo={false}

        nodeLabel="id"
        nodeColor={node => {
          if (node.group === 'entity') return '#00ffff'; // Cyan
          if (node.group === 'concept') return '#ff00ff'; // Magenta
          return '#555555'; // Grey for ghosts
        }}
        nodeOpacity={node => node.group === 'ghost' ? 0.3 : 0.9}
        nodeResolution={16}
        nodeVal={node => {
          // Calculate node size based on degree (number of links)
          const degree = graphData.links.filter(l => l.source === node.id || l.target === node.id || l.source.id === node.id || l.target.id === node.id).length;
          return node.group === 'ghost' ? 1 : Math.max(2, Math.sqrt(degree) * 1.5);
        }}

        linkOpacity={0.2}
        linkColor={() => '#00ff00'}
        linkWidth={0.5}

        onNodeClick={node => {
          // Center camera on clicked node
          if (fgRef.current) {
            const distance = 40;
            const distRatio = 1 + distance/Math.hypot(node.x, node.y, node.z);
            fgRef.current.cameraPosition(
              { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
              node, // lookAt ({ x, y, z })
              3000  // ms transition duration
            );
          }
        }}
      />
    </div>
  );
}

export default App;
