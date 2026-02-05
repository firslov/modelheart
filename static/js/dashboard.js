// Format API Key for display (show first 8 and last 4 characters)
function formatApiKey(apiKey) {
    if (!apiKey || apiKey.length <= 12) {
        return apiKey;
    }
    const firstPart = apiKey.substring(0, 8);
    const lastPart = apiKey.substring(apiKey.length - 4);
    return `${firstPart}...${lastPart}`;
}

// Load and display LLM servers and models
async function loadConfigs() {
    try {
        // Load LLM servers
        const serversResponse = await fetch('/get-llm-servers');
        const servers = await serversResponse.json();
        const serversCards = document.getElementById('llmServersCards');
        serversCards.innerHTML = '';

        for (const [url, config] of Object.entries(servers)) {
            const card = createServerCard(url, config);
            serversCards.appendChild(card);
        }

    } catch (error) {
        console.error('Error loading configs:', error);
    }
}

// Create server card for all screen sizes
function createServerCard(url, config) {
    const card = document.createElement('div');
    card.className = 'server-card';

    // Count active and inactive models
    const models = config.model || {};
    const activeModels = Object.values(models).filter(m => m.status).length;
    const totalModels = Object.keys(models).length;
    const totalRequests = Object.values(models).reduce((sum, m) => sum + (m.reqs || 0), 0);

    // Create models list HTML
    const modelsList = Object.entries(models).map(([modelName, modelConfig]) => {
        const isActive = modelConfig.status;
        const statusIcon = isActive ? 'fa-check-circle' : 'fa-times-circle';
        return `
            <div class="model-tag ${isActive ? 'active' : 'inactive'}">
                <span>${modelName}</span>
                <span style="font-family:'JetBrains Mono',monospace;">${modelConfig.reqs || 0}</span>
                <i class="fas ${statusIcon}" style="cursor:pointer;"
                   onclick="toggleModelStatus('${encodeURIComponent(url)}','${encodeURIComponent(modelName)}',${modelConfig.status})"
                       title="${isActive ? 'Active' : 'Inactive'}"></i>
            </div>
        `;
    }).join('');

    card.innerHTML = `
        <!-- Header -->
        <div class="server-url">
            ${url}
            <button onclick="copyToClipboard('${url}')" style="background:none; border:none; color:var(--text-muted); cursor:pointer; margin-left:0.5rem;" title="复制 URL">
                <i class="fas fa-copy"></i>
            </button>
        </div>
        <div class="server-device">${config.device || 'N/A'}</div>

        <!-- Stats -->
        <div class="server-stats">
            <div class="server-stat">
                <div class="server-stat-value">${activeModels}/${totalModels}</div>
                <div class="server-stat-label">活跃模型</div>
            </div>
            <div class="server-stat">
                <div class="server-stat-value">${totalRequests}</div>
                <div class="server-stat-label">请求总数</div>
            </div>
        </div>

        <!-- API Key Status -->
        <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.65rem; color:var(--text-secondary); padding:0.5rem; background:var(--bg-card); border:1px solid var(--border); margin-bottom:0.75rem;">
            <span>API Key</span>
            <div style="display:flex; align-items:center; gap:0.375rem;">
                <span style="font-family:'JetBrains Mono',monospace;">${config.apikey ? formatApiKey(config.apikey) : 'Not Set'}</span>
                ${config.apikey ? `<button onclick="copyToClipboard('${config.apikey}')" style="background:none; border:none; color:var(--text-muted); cursor:pointer;" title="复制 API Key"><i class="fas fa-copy"></i></button>` : ''}
            </div>
        </div>

        <!-- Models List -->
        <div class="server-models">
            <div class="server-models-title">可用模型</div>
            <div style="max-height:100px; overflow-y:auto;">
                ${modelsList}
            </div>
        </div>

        <!-- Actions -->
        <div class="server-actions">
            <button onclick="showEditServerModal('${encodeURIComponent(url)}')" class="action-btn">
                <i class="fas fa-edit"></i>
                <span>编辑</span>
            </button>
            <button onclick="deleteServer('${encodeURIComponent(url)}')" class="action-btn delete">
                <i class="fas fa-trash"></i>
                <span>删除</span>
            </button>
        </div>
    `;

    return card;
}

// Server management functions
function showAddServerModal() {
    // Clear the models table and add one empty row
    const tableBody = document.getElementById('addServerModelsTable');
    tableBody.innerHTML = '';
    addNewModelRow('addServer');

    document.getElementById('addServerModal').style.display = 'flex';
}

function closeAddServerModal() {
    document.getElementById('addServerModal').style.display = 'none';
    // Clear form fields
    document.getElementById('serverUrl').value = '';
    document.getElementById('serverDevice').value = '';
    document.getElementById('serverApiKey').value = '';
    document.getElementById('addServerModelsTable').innerHTML = '';
}

async function addServer() {
    const url = document.getElementById('serverUrl').value;
    const device = document.getElementById('serverDevice').value;
    const apiKey = document.getElementById('serverApiKey').value;

    if (!url || !device) {
        alert('URL and Device are required');
        return;
    }

    // Collect models from table and check for duplicates
    const models = {};
    const frontendModels = new Set();
    const rows = document.querySelectorAll('#addServerModelsTable tr');
    const duplicateModels = [];

    for (const row of rows) {
        const frontendInput = row.querySelector('.model-frontend');
        const backendInput = row.querySelector('.model-backend');
        const inputWeightInput = row.querySelector('.model-input-weight');
        const outputWeightInput = row.querySelector('.model-output-weight');
        const statusSelect = row.querySelector('.model-status');

        const frontendModel = frontendInput.value.trim();
        const backendModel = backendInput.value.trim();
        const inputWeight = parseFloat(inputWeightInput.value) || 1.0;
        const outputWeight = parseFloat(outputWeightInput.value) || 1.0;
        const status = statusSelect.value === 'true';

        if (frontendModel && backendModel) {
            // Check for duplicate frontend model names
            if (frontendModels.has(frontendModel)) {
                duplicateModels.push(frontendModel);
                // Highlight the duplicate row
                frontendInput.style.borderColor = '#ef4444';
                frontendInput.style.backgroundColor = '#fef2f2';
            } else {
                frontendModels.add(frontendModel);
                // Reset styling if not duplicate
                frontendInput.style.borderColor = '';
                frontendInput.style.backgroundColor = '';
            }

            models[frontendModel] = {
                name: backendModel,
                status: status,
                reqs: 0,
                input_token_weight: inputWeight,
                output_token_weight: outputWeight
            };
        }
    }

    // Show warning if duplicates found
    if (duplicateModels.length > 0) {
        const warningMessage = `发现重复的前端模型名称:\n${duplicateModels.join(', ')}\n\n每个前端模型名称在同一服务器中必须是唯一的。`;
        alert(warningMessage);
        return;
    }

    if (Object.keys(models).length === 0) {
        alert('At least one model configuration is required');
        return;
    }

    try {
        const response = await fetch('/update-llm-servers', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                action: 'add',
                url,
                config: {
                    device,
                    apikey: apiKey || undefined,
                    model: models
                }
            }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to add server');
        }

        closeAddServerModal();
        loadConfigs();
    } catch (error) {
        alert('Error adding server: ' + error.message);
    }
}

async function deleteServer(url) {
    if (!confirm('Are you sure you want to delete this server?')) {
        return;
    }

    try {
        const response = await fetch('/update-llm-servers', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                action: 'delete',
                url
            }),
        });

        if (!response.ok) {
            throw new Error('Failed to delete server');
        }

        loadConfigs();
    } catch (error) {
        alert('Error deleting server: ' + error.message);
    }
}

// Edit Server Modal - New Table-based Interface
function showEditServerModal(url) {
    document.getElementById('editServerUrl').value = url;
    fetch('/get-llm-servers')
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(servers => {
            const decodedUrl = decodeURIComponent(url);
            const config = servers[decodedUrl];
            if (!config) throw new Error('Server config not found');

            document.getElementById('editServerDevice').value = config.device || '';
            document.getElementById('editServerApiKey').value = config.apikey || '';

            // Populate models table instead of JSON textarea
            populateModelsTable(config.model || {});
            document.getElementById('editServerModal').style.display = 'flex';
        })
        .catch(error => {
            console.error('Error loading server details:', error);
            alert('Failed to load server details: ' + error.message);
        });
}

function closeEditServerModal() {
    document.getElementById('editServerModal').style.display = 'none';
}

function populateModelsTable(models) {
    const tableBody = document.getElementById('editServerModelsTable');
    tableBody.innerHTML = '';

    for (const [frontendModel, modelConfig] of Object.entries(models)) {
        addModelRow(
            frontendModel,
            modelConfig.name,
            modelConfig.status,
            modelConfig.reqs || 0,
            modelConfig.input_token_weight || 1.0,
            modelConfig.output_token_weight || 1.0
        );
    }
}

function addModelRow(frontendModel = '', backendModel = '', status = true, reqs = 0, inputWeight = 1.0, outputWeight = 1.0, target = 'editServer') {
    const tableBody = document.getElementById(target === 'addServer' ? 'addServerModelsTable' : 'editServerModelsTable');
    const row = document.createElement('tr');
    row.className = 'border-b hover:bg-gray-50';

    row.innerHTML = `
        <td class="px-4 py-2 border">
            <input type="text" class="w-full px-2 py-1 border rounded model-frontend" 
                   value="${frontendModel}" placeholder="Frontend model name"
                   oninput="validateModelName(this)">
        </td>
        <td class="px-4 py-2 border">
            <input type="text" class="w-full px-2 py-1 border rounded model-backend" 
                   value="${backendModel}" placeholder="Backend model name">
        </td>
        <td class="px-4 py-2 border">
            <input type="number" class="w-full px-2 py-1 border rounded model-input-weight" 
                   value="${inputWeight}" placeholder="1.0" step="0.1" min="0" title="Input token weight">
        </td>
        <td class="px-4 py-2 border">
            <input type="number" class="w-full px-2 py-1 border rounded model-output-weight" 
                   value="${outputWeight}" placeholder="1.0" step="0.1" min="0" title="Output token weight">
        </td>
        <td class="px-4 py-2 border">
            <select class="w-full px-2 py-1 border rounded model-status">
                <option value="true" ${status ? 'selected' : ''}>Active</option>
                <option value="false" ${!status ? 'selected' : ''}>Inactive</option>
            </select>
        </td>
        <td class="px-4 py-2 border">
            <div class="flex items-center space-x-2">
                <span class="text-xs text-gray-500">${reqs} reqs</span>
                <button onclick="this.closest('tr').remove()" 
                        class="text-red-500 hover:text-red-700 transition-colors" title="Remove">
                    <i class="fas fa-trash text-xs"></i>
                </button>
            </div>
        </td>
    `;

    tableBody.appendChild(row);
}

function addNewModelRow(target = 'editServer') {
    addModelRow('', '', true, 0, 1.0, 1.0, target);
}

async function updateServer() {
    const oldUrl = decodeURIComponent(document.getElementById('editServerUrl').value);
    const newUrl = decodeURIComponent(document.getElementById('editServerUrl').value); // Same URL for now
    const device = document.getElementById('editServerDevice').value;
    const apiKey = document.getElementById('editServerApiKey').value;

    if (!newUrl || !device) {
        alert('URL and Device are required');
        return;
    }

    // Collect models from table and check for duplicates
    const models = {};
    const frontendModels = new Set();
    const rows = document.querySelectorAll('#editServerModelsTable tr');
    const duplicateModels = [];

    // Get current server data once to avoid multiple API calls
    let currentServerData = null;
    try {
        const serversResponse = await fetch('/get-llm-servers');
        const servers = await serversResponse.json();
        currentServerData = servers[oldUrl];
    } catch (error) {
        // Silently continue if we can't fetch current data
    }

    for (const row of rows) {
        const frontendInput = row.querySelector('.model-frontend');
        const backendInput = row.querySelector('.model-backend');
        const inputWeightInput = row.querySelector('.model-input-weight');
        const outputWeightInput = row.querySelector('.model-output-weight');
        const statusSelect = row.querySelector('.model-status');

        const frontendModel = frontendInput.value.trim();
        const backendModel = backendInput.value.trim();
        const inputWeight = parseFloat(inputWeightInput.value) || 1.0;
        const outputWeight = parseFloat(outputWeightInput.value) || 1.0;
        const status = statusSelect.value === 'true';

        if (frontendModel && backendModel) {
            // Check for duplicate frontend model names
            if (frontendModels.has(frontendModel)) {
                duplicateModels.push(frontendModel);
                // Highlight the duplicate row
                frontendInput.style.borderColor = '#ef4444';
                frontendInput.style.backgroundColor = '#fef2f2';
            } else {
                frontendModels.add(frontendModel);
                // Reset styling if not duplicate
                frontendInput.style.borderColor = '';
                frontendInput.style.backgroundColor = '';
            }

            // Get current reqs value from existing data
            let reqs = 0;
            if (currentServerData && currentServerData.model) {
                // Try to find the model by frontend name
                const existingModel = currentServerData.model[frontendModel];
                if (existingModel) {
                    reqs = existingModel.reqs || 0;
                }
            }

            models[frontendModel] = {
                name: backendModel,
                status: status,
                reqs: reqs,
                input_token_weight: inputWeight,
                output_token_weight: outputWeight
            };
        }
    }

    // Show warning if duplicates found
    if (duplicateModels.length > 0) {
        const warningMessage = `发现重复的前端模型名称:\n${duplicateModels.join(', ')}\n\n每个前端模型名称在同一服务器中必须是唯一的。`;
        alert(warningMessage);
        return;
    }

    if (Object.keys(models).length === 0) {
        alert('At least one model configuration is required');
        return;
    }

    try {
        const response = await fetch('/update-llm-servers', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                action: 'update',
                oldUrl,
                url: newUrl,
                config: {
                    device,
                    apikey: apiKey || undefined,
                    model: models
                }
            }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to update server');
        }

        closeEditServerModal();
        loadConfigs();
    } catch (error) {
        console.error('Error updating server:', error);
        alert('Error updating server: ' + error.message);
    }
}

// Toggle model status
async function toggleModelStatus(serverUrl, modelId, currentStatus) {
    try {
        const decodedUrl = decodeURIComponent(serverUrl);
        const decodedModel = decodeURIComponent(modelId);
        const newStatus = !currentStatus;

        const response = await fetch('/update-llm-servers', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                action: 'toggle_status',
                url: decodedUrl,
                model: decodedModel,
                status: newStatus
            }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to update model status');
        }

        loadConfigs();
    } catch (error) {
        alert('Error toggling model status: ' + error.message);
    }
}


// Handle window resize for responsive layout
function handleResize() {
    // Reload configs to switch between table and card layout
    loadConfigs();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    loadConfigs();
    // Add resize listener
    window.addEventListener('resize', handleResize);
});

// Original functions
function showEditLimit(apiKey, currentLimit) {
    document.getElementById('editLimitModal').style.display = 'flex';
    document.getElementById('newLimit').value = currentLimit;
    document.getElementById('currentApiKey').value = apiKey;
}

function closeEditModal() {
    document.getElementById('editLimitModal').style.display = 'none';
}

async function updateLimit() {
    const apiKey = document.getElementById('currentApiKey').value;
    const newLimit = parseInt(document.getElementById('newLimit').value);

    if (!newLimit || newLimit <= 0) {
        alert('Please enter a valid limit');
        return;
    }

    try {
        const response = await fetch('/update-api-key-limit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                api_key: apiKey,
                new_limit: newLimit
            }),
        });

        if (!response.ok) {
            throw new Error('Failed to update limit');
        }

        // Find the corresponding API key card and update the limit
        const apiKeyCard = document.querySelector(`[data-key="${apiKey}"]`).closest('.api-key-card');
        if (apiKeyCard) {
            // Update the usage text in the progress bar section
            const usageTextElement = apiKeyCard.querySelector('.flex.justify-between.text-xs.text-gray-600.mb-1 span:last-child');
            if (usageTextElement) {
                const currentUsage = parseInt(usageTextElement.textContent.split('/')[0]);
                usageTextElement.textContent = `${currentUsage}/${newLimit}`;
            }

            // Update the progress bar data attributes and recalculate
            const progressBar = apiKeyCard.querySelector('.api-key-usage');
            if (progressBar) {
                const currentUsage = parseFloat(progressBar.getAttribute('data-usage')) || 0;
                progressBar.setAttribute('data-limit', newLimit);

                // Recalculate and update the progress bar
                const percentage = Math.min((currentUsage / newLimit) * 100, 100);

                // Update color based on new percentage
                progressBar.classList.remove('bg-indigo-500', 'bg-yellow-500', 'bg-red-500');
                if (percentage >= 90) {
                    progressBar.classList.add('bg-red-500');
                } else if (percentage >= 70) {
                    progressBar.classList.add('bg-yellow-500');
                } else {
                    progressBar.classList.add('bg-indigo-500');
                }

                // Update the progress bar width
                progressBar.style.width = percentage + '%';
            }

            // Update the edit button data-limit attribute
            const editButton = apiKeyCard.querySelector('button[onclick*="showEditLimit"]');
            if (editButton) {
                editButton.setAttribute('data-limit', newLimit);
            }
        }

        closeEditModal();
    } catch (error) {
        alert('Error updating limit: ' + error.message);
    }
}

async function resetUsage(apiKey) {
    if (!confirm('Are you sure you want to reset the usage for this API key?')) {
        return;
    }
    try {
        const response = await fetch('/reset-api-key-usage', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ api_key: apiKey }),
        });
        if (!response.ok) {
            throw new Error('Failed to reset usage');
        }
        // Refresh the page to update all usage data
        window.location.reload();
    } catch (error) {
        alert('Error resetting usage: ' + error.message);
    }
}

async function revokeKey(apiKey) {
    if (!confirm('Are you sure you want to revoke this API key?')) {
        return;
    }
    try {
        const response = await fetch('/revoke-api-key', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ api_key: apiKey }),
        });
        if (!response.ok) {
            throw new Error('Failed to revoke API key');
        }
        window.location.reload();
    } catch (error) {
        alert('Error revoking API key: ' + error.message);
    }
}

// Password Change Functions
function showChangePasswordModal(apiKey) {
    document.getElementById('changePasswordModal').style.display = 'flex';
    document.getElementById('currentApiKeyForPassword').value = apiKey;
    document.getElementById('newPassword').value = '';
}

function closeChangePasswordModal() {
    document.getElementById('changePasswordModal').style.display = 'none';
}

async function changePassword() {
    const apiKey = document.getElementById('currentApiKeyForPassword').value;
    const newPassword = document.getElementById('newPassword').value;

    if (!newPassword) {
        alert('请输入新密码');
        return;
    }

    if (newPassword.length < 6) {
        alert('密码长度至少6位');
        return;
    }

    if (newPassword.length > 72) {
        alert('密码长度不能超过72个字符');
        return;
    }

    if (!confirm('确定要修改该用户的密码吗？')) {
        return;
    }

    try {
        const response = await fetch('/change-user-password', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                api_key: apiKey,
                new_password: newPassword
            }),
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || '修改密码失败');
        }

        alert('密码修改成功');
        closeChangePasswordModal();
    } catch (error) {
        alert('修改密码失败: ' + error.message);
    }
}

// Model Usage Functions
async function toggleModelUsage(apiKey) {
    const container = document.querySelector(`.model-usage-container[data-key="${apiKey}"]`);
    if (!container) {
        console.error('Container not found for API key:', apiKey);
        return;
    }

    const existingDetails = container.querySelector('.model-usage-details');

    if (existingDetails) {
        existingDetails.remove();
        return;
    }

    // Show loading state - find the specific toggle button
    const button = container.closest('.api-key-card').querySelector('button[onclick*="toggleModelUsage"]');
    if (!button) {
        console.error('Toggle button not found for API key:', apiKey);
        return;
    }

    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Loading...';
    button.disabled = true;

    try {
        // Get model usage data from the page data
        const apiKeysDataElement = document.getElementById('apiKeysData');
        if (!apiKeysDataElement) {
            throw new Error('API keys data element not found');
        }

        const apiKeys = JSON.parse(apiKeysDataElement.textContent);
        const currentKey = apiKeys.find(key => key.key === apiKey);

        if (!currentKey || !currentKey.model_usage) {
            button.innerHTML = originalText;
            button.disabled = false;
            return;
        }

        const details = createModelUsageDetails(currentKey.model_usage);
        container.appendChild(details);

    } catch (error) {
        console.error('Error loading model usage data:', error);
        // Show error message
        const details = document.createElement('div');
        details.className = 'model-usage-details mt-3 p-4 bg-red-50 rounded-lg border border-red-200';
        details.innerHTML = `
            <div class="text-red-700 text-sm">
                <i class="fas fa-exclamation-triangle mr-2"></i>
                Failed to load model usage data
            </div>
        `;
        container.appendChild(details);
    } finally {
        // Restore button state
        button.innerHTML = originalText;
        button.disabled = false;
    }
}

function createModelUsageDetails(modelUsage) {
    const details = document.createElement('div');
    details.className = 'model-usage-details mt-3 bg-gray-50 rounded-lg border border-gray-200';

    // Create a scrollable container for the table
    const tableContainer = document.createElement('div');
    tableContainer.className = 'overflow-x-auto max-h-64 custom-scrollbar';

    const table = document.createElement('table');
    table.className = 'w-full text-xs min-w-full';

    const header = document.createElement('thead');
    header.className = 'sticky top-0 bg-gray-100 z-10';
    header.innerHTML = `
        <tr>
            <th class="px-2 py-2 text-left font-medium text-gray-500 uppercase tracking-wider border-b">Model</th>
            <th class="px-2 py-2 text-left font-medium text-gray-500 uppercase tracking-wider border-b">Requests</th>
            <th class="px-2 py-2 text-left font-medium text-gray-500 uppercase tracking-wider border-b">Tokens</th>
            <th class="px-2 py-2 text-left font-medium text-gray-500 uppercase tracking-wider border-b">Avg/Req</th>
        </tr>
    `;

    const body = document.createElement('tbody');
    body.className = 'bg-white divide-y divide-gray-200';

    // Sort models by usage (highest tokens first)
    const sortedModels = Object.entries(modelUsage).sort((a, b) => b[1].tokens - a[1].tokens);

    sortedModels.forEach(([model, usage]) => {
        const row = document.createElement('tr');
        const avgTokens = usage.requests > 0 ? (usage.tokens / usage.requests).toFixed(1) : '0';

        // Truncate long model names
        const displayModel = model.length > 20 ? model.substring(0, 17) + '...' : model;

        row.innerHTML = `
            <td class="px-2 py-1 whitespace-nowrap font-medium text-gray-900" title="${model}">${displayModel}</td>
            <td class="px-2 py-1 whitespace-nowrap text-gray-500 text-right">${usage.requests}</td>
            <td class="px-2 py-1 whitespace-nowrap text-gray-500 text-right">${usage.tokens.toFixed(0)}</td>
            <td class="px-2 py-1 whitespace-nowrap text-gray-500 text-right">${avgTokens}</td>
        `;
        body.appendChild(row);
    });

    table.appendChild(header);
    table.appendChild(body);
    tableContainer.appendChild(table);
    details.appendChild(tableContainer);

    // Add summary row if there are many models
    if (sortedModels.length > 5) {
        const totalRequests = sortedModels.reduce((sum, [_, usage]) => sum + usage.requests, 0);
        const totalTokens = sortedModels.reduce((sum, [_, usage]) => sum + usage.tokens, 0);

        const summaryDiv = document.createElement('div');
        summaryDiv.className = 'px-3 py-2 bg-gray-100 border-t border-gray-200 text-xs text-gray-600';
        summaryDiv.innerHTML = `
            <div class="flex justify-between">
                <span>Total: ${sortedModels.length} models</span>
                <span>${totalRequests} requests, ${totalTokens.toFixed(0)} tokens</span>
            </div>
        `;
        details.appendChild(summaryDiv);
    }

    return details;
}

// Real-time validation for model names
function validateModelName(inputElement) {
    const table = inputElement.closest('tbody');
    const rows = table.querySelectorAll('tr');
    const currentValue = inputElement.value.trim();
    
    // Reset styling
    inputElement.style.borderColor = '';
    inputElement.style.backgroundColor = '';
    
    if (!currentValue) {
        return;
    }
    
    // Check for duplicates
    let duplicateCount = 0;
    rows.forEach(row => {
        const otherInput = row.querySelector('.model-frontend');
        if (otherInput && otherInput !== inputElement && otherInput.value.trim() === currentValue) {
            duplicateCount++;
        }
    });
    
    if (duplicateCount > 0) {
        inputElement.style.borderColor = '#ef4444';
        inputElement.style.backgroundColor = '#fef2f2';
        
        // Show warning tooltip
        if (!inputElement.title.includes('重复')) {
            inputElement.title = `前端模型名称重复！已有 ${duplicateCount} 个相同的名称。`;
        }
    } else {
        inputElement.title = '';
    }
}

// Initialize model usage data
document.addEventListener('DOMContentLoaded', function () {
    // Store API keys data for model usage
    // Data will be passed from the template via a global variable
    if (typeof window.apiKeysData !== 'undefined') {
        const dataElement = document.createElement('div');
        dataElement.id = 'apiKeysData';
        dataElement.style.display = 'none';
        dataElement.textContent = JSON.stringify(window.apiKeysData);
        document.body.appendChild(dataElement);
    }
});
