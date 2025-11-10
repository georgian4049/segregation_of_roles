const findingProfileMap = new Map();

// --- API Helper ---
async function fetchApi(url, options = {}, buttonElement = null) {
    if (buttonElement) showLoading(buttonElement);
    try {
        const resp = await fetch(url, options);
        if (!resp.ok) {
            let errorMsg = `API Error: ${resp.status}`;
            try {
                const errorData = await resp.json();
                if (errorData.detail) {
                    if (Array.isArray(errorData.detail)) {
                        errorMsg = errorData.detail.map(e => `${e.loc ? e.loc.join('.') : 'error'} - ${e.msg}`).join('; ');
                    } else {
                        errorMsg = errorData.detail;
                    }
                } else {
                    errorMsg = errorData.message || "Unknown error";
                }
            } catch (e) {
                const text = await resp.text();
                errorMsg = text.substring(0, 200) || errorMsg;
            }
            throw new Error(errorMsg);
        }
        const text = await resp.text();
        return text ? JSON.parse(text) : {};
    } catch (e) {
        console.error(`Error in fetchApi for ${url}:`, e);
        throw e;
    } finally {
        if (buttonElement) hideLoading(buttonElement);
    }
}

// --- Utility Functions  ---
function showLoading(buttonElement) {
    if (!buttonElement) return;
    const spinner = document.createElement('span');
    spinner.className = 'loading';
    buttonElement.appendChild(spinner);
    buttonElement.disabled = true;
}

function hideLoading(buttonElement) {
    if (!buttonElement) return;
    const spinner = buttonElement.querySelector('.loading');
    if (spinner) spinner.remove();
    buttonElement.disabled = false;
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.style.display = 'block';
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.style.display = 'none';
}

window.onclick = function(event) {
    if (event.target.classList.contains('modal-overlay')) {
        event.target.style.display = 'none';
    }
}

function resetErrorLinks() {
    const assignLink = document.getElementById('assignmentErrorsLink');
    const policyLink = document.getElementById('policyErrorsLink');
    if (assignLink) assignLink.style.display = 'none';
    if (policyLink) policyLink.style.display = 'none';
}
// --- End Utility Functions ---


function updateLLMStatus(status) {
    const banner = document.getElementById('llmStatusBanner');
    const text = document.getElementById('llmStatusText');
    if (!banner || !text) return;
    if (!status) {
        banner.style.display = 'none';
        return;
    }
    const forceShow = status.using_mock && status.fallback;
    if (banner.dataset.dismissed === 'true' && !forceShow) return;
    banner.dataset.dismissed = 'false';
    if (status.using_mock) {
        banner.className = 'status warning';
        text.textContent = status.fallback
            ? '⚠️ LLM implementation failed, using mock fallback'
            : '⚠️ Using mock LLM (configured)';
    } else {
        banner.className = 'status success';
        text.textContent = '✓ AI generated response for justification';
    }
    banner.style.display = 'block';
}

function dismissLLMStatus(event) {
    const banner = document.getElementById('llmStatusBanner');
    if (banner) {
        banner.dataset.dismissed = 'true';
        banner.style.display = 'none';
    }
    if (event) event.stopPropagation();
}


async function loadSeedData() {
    
    console.warn("loadSeedData is not implemented in the cleaned routes.");
}
async function resetData() {
    
    console.warn("resetData is not implemented in the cleaned routes.");
}


async function uploadFiles() {
    const assignFile = document.getElementById('assignmentsFile').files[0];
    const policyFile = document.getElementById('policiesFile').files[0];
    const status = document.getElementById('ingestStatus');
    resetErrorLinks();

    if (!assignFile) {
        status.className = 'status error';
        status.textContent = '✗ Please select at least an assignments CSV file.';
        return;
    }

    const formData = new FormData();
    formData.append('assignments', assignFile);
    if (policyFile) formData.append('policies', policyFile);

    try {
        const data = await fetchApi('/api/v1/ingest', { method: 'POST', body: formData }, event.target);
        status.className = 'status success';
        status.textContent = `✓ Loaded ${data.valid_assignment_rows} assignments, ${data.valid_policies} policies. Found ${data.active_users} active users.`;
        
        if (data.corrupt_assignment_rows > 0) {
            document.getElementById('assignmentErrorsLink').style.display = 'inline-block';
        }
        if (data.corrupt_policies > 0 || data.filtered_policies_single_role > 0) {
            document.getElementById('policyErrorsLink').style.display = 'inline-block';
        }
    } catch (e) {
        status.className = 'status error';
        status.textContent = '✗ Error: ' + (e.message || 'Unknown error occurred');
    }
}

async function loadFindings() {
    const btn = event.target;
    if (btn) showLoading(btn);

    const container = document.getElementById('findingsContainer');
    const countSpan = document.getElementById('findingsCount');
    const statsSection = document.getElementById('statsSection');
    
    // Set up the table structure immediately
    container.innerHTML = '<table><thead><tr><th>User Details</th><th>Violation Profile</th><th>LLM Remediation</th><th>Simulation</th><th>Actions</th></tr></thead><tbody></tbody></table>';
    const tableBody = container.querySelector('tbody');
    
    statsSection.style.display = 'none';
    findingProfileMap.clear();
    
    let findingsCount = 0;
    let profilesForStats = []; // To build the stats table at the end
    countSpan.textContent = `(Streaming...)`;

    try {
        // 1. Create an EventSource to listen to our stream
        const evtSource = new EventSource("/api/v1/findings");

        // 2. This listener is called for *every* 'data:' message
        evtSource.onmessage = (event) => {
            const item = JSON.parse(event.data);

            // Check for an error message from the stream
            if (item.error) {
                console.error("Failed to process finding for:", item.user_id, item.message);
                tableBody.innerHTML += `<tr><td colspan="5"><div class="status error">Failed to load finding for ${item.user_id}: ${item.message}</div></td></tr>`;
                return;
            }
            
            
            const profile = item.profile;
            const justification = item.justification;
            const user = profile.user;
            
            
            if (!profile) {
                return; 
                
            }

            findingsCount++;
            countSpan.textContent = `(${findingsCount} user${findingsCount !== 1 ? 's' : ''} found...)`;
            
            // Store data for other functions
            findingProfileMap.set(user.user_id, profile);
            profilesForStats.push(item); // Store the full FindingResponse
            
            const statusBadge = user.status === 'active'
                ? `<span class="badge badge-green">${user.status}</span>`
                : `<span class.badge badge-yellow">${user.status}</span>`;
            
            const roleBadges = Array.from(profile.conflicting_role_set).map(role => {
                const roleObject = user.active_roles[role];
                const system = roleObject ? roleObject.source_system : 'unknown';
                
                return `<span class="badge badge-red">${role} (${system})</span>`;
            }).join(' ');

            const policyList = profile.violated_policies.map(p => 
               
                `<li>Users hold ${p.roles.join(" + ")} <strong> (${p.policy_id})</strong></li>`
            ).join('');
            
            const userId = user.user_id;
            
            // --- Render the Justification ---
            let justificationHtml = '';
            if (justification) {
                const isMock = justification.model_identifier.includes('mock');
                const sourceBadge = isMock
                    ? '<span class="badge badge-yellow" style="margin-bottom: 8px; display: inline-block;">Mock Response</span>'
                    : '<span class="badge badge-green" style="margin-bottom: 8px; display: inline-block;">AI Generated</span>';
                
                justificationHtml = `${sourceBadge}<pre><strong>Risk:</strong> ${justification.risk}\n\n<strong>Action:</strong> ${justification.action}\n\n<strong>Rationale:</strong> ${justification.rationale}</pre>`;
            } else {
                justificationHtml = `<div class="status error" style="font-size: 0.8em; padding: 8px;">✗ Justification data missing.</div>`;
            }

            // Create the new row element
            const row = document.createElement('tr');
            row.className = 'user-row';
            row.id = `finding-row-${userId}`;
            
            
            row.innerHTML = `
                <td>
                    <strong>${user.name}</strong><br>
                    <small>${user.email.split('@')[0][0]}***@${user.email.split('@')[1]}</small><br>
                    <span class="badge badge-blue">${user.department}</span>
                    ${statusBadge}
                    <br><br><small>Finding ID: ${profile.finding_id}</small>
                </td>
                <td>
                    <small>${profile.reason}</small> 
                    <ul style="margin-left: 20px; margin-top: 5px;">${policyList}</ul>
                    <small style="margin-top: 8px; display: block;">Conflicting Roles:</small>
                    <div>${roleBadges}</div>
                </td>
                <td id="justification-cell-${userId}">
                    ${justificationHtml}
                </td>
                <td>
                    <div class="simulator">
                        <label style="font-weight: 600; font-size: 0.9em;">Simulate removal:</label>
                        <div class="simulator-controls" style="display: flex; flex-direction: column; gap: 8px; align-items: flex-start; margin-top: 5px;">
                            <select id="sim-role-${userId}" style="width: 100%;"></select>
                            <button id="sim-btn-${userId}" class="secondary small" onclick="simulateRole('${userId}', 'sim-role-${userId}')">Simulate</button>
                        </div>
                    </div>
                </td>
                <td id="action-cell-${userId}">
                    <button class="small" onclick="openDecisionModal('${userId}')">
                        Take Action
                    </button>
                </td>
            `;
            
            // 4. Append the new row to the table body
            tableBody.appendChild(row);

            // 5. Populate the dropdown for the new row
            const selectEl = document.getElementById(`sim-role-${userId}`);
            if (selectEl) {
                const conflictingRoles = Array.from(profile.conflicting_role_set);
                selectEl.innerHTML = conflictingRoles.map(r => `<option value="${r}">${r}</option>`).join('');
            }
        };

        
        evtSource.addEventListener('done', (event) => {
            console.log("Received 'done' event. Closing stream.");
            evtSource.close(); // Cleanly close the connection
            if (btn) hideLoading(btn); // Now we hide the loading spinner
            
            if (findingsCount === 0) {
                 container.innerHTML = '<div class="empty-state"><p>✅ No violations found. All users have safe role combinations.</p></div>';
                 countSpan.textContent = '(0 users in violation)';
            } else {
                countSpan.textContent = `(${findingsCount} user${findingsCount !== 1 ? 's' : ''} in violation)`;
                // Now that we have all data, render the stats table
                renderStatisticsTable(profilesForStats);
                statsSection.style.display = 'block';
            }
        });
        

        // 4. This listener now ONLY handles *real* network errors
        evtSource.onerror = (err) => {
            console.error("EventSource failed:", err);
            // Only show "Connection lost" if no findings were ever found
            if (findingsCount === 0) {
                countSpan.textContent = ""
                container.innerHTML = `<div class="status success"> No users have violated policy.</div>`;
            } else {
                
                countSpan.textContent = `(${findingsCount} found. Stream interrupted.)`;
            }
            evtSource.close();
            if (btn) hideLoading(btn);
        };

    } catch (e) {
        console.error('Load findings error:', e);
        container.innerHTML = `<div class="status error">✗ Failed to load findings: ${e.message || 'Unknown error'}</div>`;
        countSpan.textContent = '(error)';
        if (btn) hideLoading(btn);
    }
}
function renderStatisticsTable(findingProfiles) {
    const container = document.getElementById('policySummaryContainer');
    const policyCounts = {};
    const policyDescriptions = {};

    findingProfiles.forEach(item => {
        item.profile.violated_policies.forEach(policy => {
            const policyId = policy.policy_id;
            policyCounts[policyId] = (policyCounts[policyId] || 0) + 1;
            if (!policyDescriptions[policyId]) {
                policyDescriptions[policyId] = policy.description;
            }
        });
    });

    let html = '<h4 style="margin-bottom: 10px;">Violations by Policy</h4>';
    html += '<table><thead><tr><th>Policy ID</th><th>Description</th><th>Violation Count (by user)</th></tr></thead><tbody>';
    const sortedPolicies = Object.entries(policyCounts).sort((a, b) => b[1] - a[1]);
    sortedPolicies.forEach(([policyId, count]) => {
        html += `
            <tr>
                <td><strong>${policyId}</strong></td>
                <td>${policyDescriptions[policyId]}</td>
                <td><span class="badge badge-red" style="font-weight: bold; font-size: 0.9em;">${count}</span></td>
            </tr>
        `;
    });
    html += '</tbody></table>';
    container.innerHTML = html;
}


// --- THIS IS THE RESTORED SIMULATE FUNCTION ---
async function simulateRole(userId, selectElementId) {
    const select = document.getElementById(selectElementId);
    const btn = select.nextElementSibling;
    const modalTitle = document.getElementById('simModalTitle');
    const modalBody = document.getElementById('simModalBody');
    
    if (!select || !btn || !modalTitle || !modalBody) {
        console.error('Simulation modal elements not found');
        return;
    }

    const role = select.value;
    if (!role) {
        modalBody.innerHTML = '<div class="status error">✗ Select a role to simulate.</div>';
        openModal('simulationModal');
        return;
    }

    modalTitle.textContent = `Simulation: Removing '${role}'`;
    modalBody.innerHTML = '<div class="empty-state"><p>Running simulation...</p></div>';
    openModal('simulationModal');

    try {
        const data = await fetchApi('/api/v1/simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, role_to_remove: role })
        }, btn); 
        

        let html = '';
        if (data.resolved) {
            html += `<div class="status success">✓ ${data.message}</div>`;
        } else {
            html += `<div class="status warning">⚠️ ${data.message}</div>`;
            
            
            if (data.violations_remaining && data.violations_remaining.length > 0) {
                html += '<h4 style="margin-top: 20px; margin-bottom: 10px;">Remaining Violated Policy IDs:</h4>';
                html += '<ul>';
                data.violations_remaining.forEach(policyId => {
                    html += `<li style="margin-bottom: 10px;"><strong>${policyId}</strong></li>`;
                });
                html += '</ul>';
            }
        }
        
        html += '<br><small style="color: #666;">Note: This is a simulation. No data has been changed.</small>';
        modalBody.innerHTML = html;

    } catch (e) {
        modalBody.innerHTML = `<div class="status error">✗ ${e.message || 'Unknown error occurred'}</div>`;
    }
}

function openDecisionModal(userId) {
    const profile = findingProfileMap.get(userId);
    if (!profile) {
        console.error("Could not find profile for user", userId);
        return;
    }

    document.getElementById('decisionForm').reset();
    document.getElementById('decisionStatus').style.display = 'none';
    document.getElementById('revokeRoleGroup').style.display = 'none';
    
    document.getElementById('decisionUserId').value = userId;
    document.getElementById('decisionModalTitle').textContent = `Submit Decision for ${userId}`;
    document.getElementById('decisionBy').value = 'n26_manager';

    const checkboxContainer = document.getElementById('decisionRoleCheckboxes');
    checkboxContainer.innerHTML = '';
    
    const conflictingRoles = Array.from(profile.conflicting_role_set);
    
    if (conflictingRoles.length === 0) {
        checkboxContainer.innerHTML = "No conflicting roles found to revoke.";
    } else {
        conflictingRoles.forEach(role => {
            const system = profile.user.active_roles[role] || 'unknown';
            const id = `role-revoke-${role}`;
            checkboxContainer.innerHTML += `
                <div style="margin-bottom: 5px;">
                    <input type="checkbox" name="roles_to_revoke" value="${role}" id="${id}">
                    <label for="${id}" style="font-weight: normal; display: inline-block; margin-left: 5px;">${role} (from ${system.source_system})</label>
                </div>
            `;
        });
    }
    
    openModal('decisionModal');
}

function toggleRevokeRole(decision) {
    const revokeGroup = document.getElementById('revokeRoleGroup');
    if (decision === 'revoke_role') {
        revokeGroup.style.display = 'block';
    } else {
        revokeGroup.style.display = 'none';
    }
}

async function submitDecision(event) {
    event.preventDefault();
    const btn = document.getElementById('decisionSubmitBtn');
    const statusDiv = document.getElementById('decisionStatus');
    statusDiv.style.display = 'none';
    
    const form = document.getElementById('decisionForm');
    const formData = new FormData(form);
    
    const payload = {
        user_id: formData.get('user_id'),
        decision: formData.get('decision'),
        notes: formData.get('notes'),
        decided_by: formData.get('decided_by'),
        roles_to_revoke: formData.getAll('roles_to_revoke')
    };
    
    if (!payload.decision) {
        statusDiv.className = 'status error';
        statusDiv.textContent = 'Please select a decision.';
        statusDiv.style.display = 'block';
        return;
    }
    if (payload.decision === 'revoke_role' && payload.roles_to_revoke.length === 0) {
        statusDiv.className = 'status error';
        statusDiv.textContent = 'Please select at least one role to revoke.';
        statusDiv.style.display = 'block';
        return;
    }
    if (payload.decision !== 'revoke_role') {
        payload.roles_to_revoke = [];
    }
    
    try {
        const data = await fetchApi('/api/v1/decisions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }, btn);
        
        statusDiv.className = 'status success';
        statusDiv.textContent = `✓ ${data.message}`;
        statusDiv.style.display = 'block';
        
        const actionCell = document.getElementById(`action-cell-${payload.user_id}`);
        if (actionCell) {
            actionCell.innerHTML = `<div class="decision-badge">✓ Decision Logged</div>`;
        }
        const row = document.getElementById(`finding-row-${payload.user_id}`);
        if (row) row.classList.add('decision-made');
        
        setTimeout(() => closeModal('decisionModal'), 1000);
        
    } catch(e) {
        statusDiv.className = 'status error';
        statusDiv.textContent = `✗ ${e.message || 'Unknown error'}`;
        statusDiv.style.display = 'block';
    }
}

async function downloadEvidence() {
    const btn = event.target;
    let status = btn.parentElement.querySelector('.status');
    if (status) status.remove();

    try {
        showLoading(btn);
        const resp = await fetch('/api/v1/evidence');
        if (!resp.ok) {
            let errorMsg = `API error: ${resp.status}`;
            try {
                const errorData = await resp.json();
                errorMsg = errorData.detail || errorData.message || errorMsg;
            } catch (parseError) {  }
            throw new Error(errorMsg);
        }
        
        const data = await resp.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `sod-evidence-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
        a.click();
        URL.revokeObjectURL(url);

    } catch (e) {
        status = document.createElement('div');
        status.className = 'status error';
        status.textContent = '✗ ' + e.message;
        btn.parentElement.appendChild(status);
        setTimeout(() => status.remove(), 4000);
    } finally {
        hideLoading(btn);
    }
}