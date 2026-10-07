let currentMap = null;
let currentGeojsonLayer = null;
let allFeatures = [];
let currentFileId = null;

document.addEventListener("DOMContentLoaded", () => {
    initMap();
    setupDropzone();
    loadRecentFiles();
});

function initMap() {
    currentMap = L.map('map', {
        center: [20.5937, 78.9629],
        zoom: 4,
        zoomControl: true
    });

    // High quality dark tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(currentMap);
}

function setupDropzone() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileUpload(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileUpload(fileInput.files[0]);
        }
    });
}

async function handleFileUpload(file) {
    const statusBox = document.getElementById('status-container');
    statusBox.innerHTML = `
        <div class="loading-overlay">
            <div class="spinner"></div>
            <p>Uploading and processing <strong>${file.name}</strong>...</p>
            <p style="font-size:0.75rem;">Reprojecting geometries to UTM & calculating measurements...</p>
        </div>
    `;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/files/', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Upload failed');
        }

        const fileInfo = await response.json();
        currentFileId = fileInfo.id;
        renderFileInfo(fileInfo);
        await loadMeasurements(fileInfo.id);
        await loadMapFeatures(fileInfo.id);
        loadRecentFiles();
    } catch (error) {
        statusBox.innerHTML = `
            <div style="color: var(--danger); padding: 20px; text-align: center;">
                <h4>Upload Error</h4>
                <p style="font-size: 0.85rem; margin-top: 6px;">${error.message}</p>
            </div>
        `;
    }
}

async function loadMeasurements(fileId) {
    try {
        const res = await fetch(`/api/files/${fileId}/measurements/?include_geometry=true`);
        if (!res.ok) throw new Error("Failed to load measurements");
        const data = await res.json();
        
        renderSummaryMetrics(data.summary);
        allFeatures = data.features;
        renderFeaturesTable(allFeatures);
    } catch (err) {
        console.error(err);
    }
}

async function loadMapFeatures(fileId) {
    try {
        const res = await fetch(`/api/files/${fileId}/features/`);
        if (!res.ok) return;
        const geojsonData = await res.json();

        if (currentGeojsonLayer) {
            currentMap.removeLayer(currentGeojsonLayer);
        }

        currentGeojsonLayer = L.geoJSON(geojsonData, {
            style: (feature) => {
                const type = feature.geometry?.type;
                if (type && type.includes('Polygon')) {
                    return { color: '#6366f1', weight: 2, fillColor: '#818cf8', fillOpacity: 0.45 };
                }
                return { color: '#06b6d4', weight: 3, opacity: 0.85 };
            },
            pointToLayer: (feature, latlng) => {
                return L.circleMarker(latlng, {
                    radius: 6,
                    fillColor: '#f59e0b',
                    color: '#fff',
                    weight: 1.5,
                    opacity: 1,
                    fillOpacity: 0.85
                });
            },
            onEachFeature: (feature, layer) => {
                const props = feature.properties || {};
                let popupContent = `<div style="font-family: sans-serif; font-size: 12px; min-width: 160px;">`;
                popupContent += `<strong>Feature #${feature.id}</strong><br>`;
                popupContent += `<span style="color:#6366f1; font-weight:600;">Type: ${feature.geometry.type}</span><br>`;
                
                if (props._formatted_value) {
                    popupContent += `<strong>Measurement:</strong> ${props._formatted_value}<br>`;
                }
                if (props._projected_crs) {
                    popupContent += `<strong>Projected CRS:</strong> <code>${props._projected_crs}</code><br>`;
                }
                
                // Add attributes
                popupContent += `<hr style="margin: 6px 0; border: none; border-top: 1px solid #e2e8f0;">`;
                popupContent += `<strong>Attributes:</strong><br>`;
                for (const [key, val] of Object.entries(props)) {
                    if (!key.startsWith('_')) {
                        popupContent += `<em>${key}:</em> ${val}<br>`;
                    }
                }
                popupContent += `</div>`;
                layer.bindPopup(popupContent);
            }
        }).addTo(currentMap);

        if (currentGeojsonLayer.getBounds().isValid()) {
            currentMap.fitBounds(currentGeojsonLayer.getBounds(), { padding: [30, 30] });
        }
    } catch (err) {
        console.error("Map feature load error:", err);
    }
}

function renderFileInfo(info) {
    const statusBox = document.getElementById('status-container');
    const badgeClass = info.status === 'COMPLETED' ? 'badge-completed' : (info.status === 'PROCESSING' ? 'badge-processing' : 'badge-failed');
    
    statusBox.innerHTML = `
        <div class="file-info-box">
            <div class="info-row">
                <span>File Name</span>
                <span>${info.filename}</span>
            </div>
            <div class="info-row">
                <span>File ID</span>
                <span style="font-family: monospace; font-size: 0.8rem;">${info.id}</span>
            </div>
            <div class="info-row">
                <span>Format</span>
                <span>${info.file_type.toUpperCase()}</span>
            </div>
            <div class="info-row">
                <span>Feature Count</span>
                <span>${info.feature_count} features</span>
            </div>
            <div class="info-row">
                <span>Source CRS</span>
                <span class="crs-tag">${info.crs}</span>
            </div>
            <div class="info-row">
                <span>Processing Status</span>
                <span class="badge ${badgeClass}">${info.status}</span>
            </div>
        </div>
    `;
}

function renderSummaryMetrics(summary) {
    document.getElementById('metric-total-features').innerText = summary.total_features;
    document.getElementById('metric-polygons').innerText = `${summary.polygon_count} Polygons`;
    document.getElementById('metric-area').innerText = `${summary.total_area_sq_meters.toLocaleString()} m²`;
    document.getElementById('metric-area-sub').innerText = `${summary.total_area_hectares.toFixed(3)} ha | ${summary.total_area_sq_km.toFixed(4)} km²`;
    
    document.getElementById('metric-lines').innerText = `${summary.linestring_count} Lines`;
    document.getElementById('metric-length').innerText = `${summary.total_length_meters.toLocaleString()} m`;
    document.getElementById('metric-length-sub').innerText = `${summary.total_length_km.toFixed(3)} km`;
    
    document.getElementById('metric-points').innerText = `${summary.point_count} Points`;
    document.getElementById('metric-points-sub').innerText = `Measurements Skipped (N/A)`;
}

function renderFeaturesTable(features) {
    const tbody = document.getElementById('features-table-body');
    tbody.innerHTML = '';

    if (!features || features.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">No features found.</td></tr>`;
        return;
    }

    features.forEach(f => {
        const tr = document.createElement('tr');
        
        let measDisplay = f.formatted_value;
        if (f.status === 'skipped_point') {
            measDisplay = `<span style="color: var(--warning);">N/A (Point)</span>`;
        } else if (f.status === 'unsupported_geometry') {
            measDisplay = `<span style="color: var(--danger);">Unsupported</span>`;
        }

        const propsSummary = Object.keys(f.properties || {}).length > 0 
            ? JSON.stringify(f.properties) 
            : '<span style="color:var(--text-dim);">None</span>';

        tr.innerHTML = `
            <td><strong>#${f.feature_id}</strong></td>
            <td><span class="type-tag type-${f.geometry_type}">${f.geometry_type}</span></td>
            <td><span style="text-transform: capitalize; font-weight: 500;">${f.measurement_type}</span></td>
            <td><strong>${measDisplay}</strong></td>
            <td><span class="crs-tag">${f.projected_crs || '—'}</span></td>
            <td><span style="font-size:0.75rem; color:${f.status === 'success' ? '#34d399' : '#fbbf24'};">${f.status}</span></td>
            <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: monospace; font-size: 0.75rem;" title='${propsSummary}'>
                ${propsSummary}
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function filterFeatures() {
    const typeFilter = document.getElementById('geom-filter').value;
    const searchVal = document.getElementById('search-filter').value.toLowerCase();

    const filtered = allFeatures.filter(f => {
        const matchesType = !typeFilter || f.geometry_type === typeFilter;
        const matchesSearch = !searchVal || 
            String(f.feature_id).includes(searchVal) ||
            f.geometry_type.toLowerCase().includes(searchVal) ||
            JSON.stringify(f.properties || {}).toLowerCase().includes(searchVal);
        return matchesType && matchesSearch;
    });

    renderFeaturesTable(filtered);
}

function exportMeasurementsJSON() {
    if (!allFeatures || allFeatures.length === 0) {
        alert("No measurement data available to export.");
        return;
    }
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(allFeatures, null, 2));
    const dlAnchor = document.createElement('a');
    dlAnchor.setAttribute("href", dataStr);
    dlAnchor.setAttribute("download", `measurements_${currentFileId || 'export'}.json`);
    dlAnchor.click();
}

async function loadRecentFiles() {
    try {
        const res = await fetch('/api/files/?limit=5');
        if (!res.ok) return;
        const files = await res.json();
        const container = document.getElementById('recent-files-list');
        if (!container) return;

        if (files.length === 0) {
            container.innerHTML = '<span style="color:var(--text-dim);">No files uploaded yet.</span>';
            return;
        }

        container.innerHTML = files.map(f => `
            <button class="btn-sample" onclick="loadExistingFile('${f.id}')">
                ${f.filename} (${f.feature_count} feats)
            </button>
        `).join('');
    } catch (e) {
        console.error(e);
    }
}

async function loadExistingFile(fileId) {
    currentFileId = fileId;
    try {
        const res = await fetch(`/api/files/${fileId}/`);
        if (!res.ok) return;
        const fileInfo = await res.json();
        renderFileInfo(fileInfo);
        await loadMeasurements(fileId);
        await loadMapFeatures(fileId);
    } catch (e) {
        console.error(e);
    }
}
