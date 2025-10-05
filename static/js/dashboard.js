// Load and display LLM servers and models
async function loadConfigs() {
    try {
        // Load LLM servers
        const serversResponse = await fetch('/get-llm-servers');
        const servers = await serversResponse.json();
        const serversTable = document.getElementById('llmServersTable');
        serversTable.innerHTML = '';

        // Check if we're on mobile
        const isMobile = window.innerWidth <= 768;

        for (const [url, config] of Object.entries(servers)) {
            if (isMobile) {
                // Mobile: Use card layout
                const card = createServerCard(url, config);
                serversTable.appendChild(card);
            } else {
                // Desktop: Use table layout
                const row = createServerTableRow(url, config);
                serversTable.appendChild(row);
            }
        }

    } catch (error) {
        console.error('Error loading configs:', error);
    }
}

// Create server card for mobile view
function createServerCard(url, config) {
    const card = document.createElement('div');
    card.className = 'llm-server-card';
    
    // Count active and inactive models
    const models = config.model || {};
    const activeModels = Object.values(models).filter(m => m.status).length;
    const totalModels = Object.keys(models).length;
    
    // Create models list HTML
    const modelsList = Object.entries(models).map(([modelName, modelConfig]) => {
        const statusClass = modelConfig.status ? '' : 'inactive';
        return `<span class="llm-server-model-tag ${statusClass}">${modelName}</span>`;
    }).join('');
    
    card.innerHTML = `
        <div class="llm-server-header">
            <div class="llm-server-url">${url}</div>
            <div class="llm-server-actions">
                <button onclick="showEditServerModal('${encodeURIComponent(url)}')" 
                        class="text-indigo-600 hover:text-indigo-800" title="Edit">
                    <i class="fas fa-edit"></i>
                </button>
                <button onclick="deleteServer('${encodeURIComponent(url)}')" 
                        class="text-red-600 hover:text-red-800" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
        <div class="llm-server-info">
            <div class="llm-server-info-item">
                <span class="llm-server-info-label">Device</span>
                <span class="llm-server-info-value">${config.device || 'N/A'}</span>
            </div>
            <div class="llm-server-info-item">
                <span class="llm-server-info-label">API Key</span>
                <span class="llm-server-info-value">${config.apikey ? 'Set' : 'Not Set'}</span>
            </div>
            <div class="llm-server-info-item">
                <span class="llm-server-info-label">Models</span>
                <span class="llm-server-info-value">${activeModels}/${totalModels} Active</span>
            </div>
            <div class="llm-server-info-item">
                <span class="llm-server-info-label">Total Reqs</span>
                <span class="llm-server-info-value">${Object.values(models).reduce((sum, m) => sum + (m.reqs || 0), 0)}</span>
            </div>
        </div>
        <div class="llm-server-models">
            <div class="llm-server-models-label">Available Models</div>
            <div class="llm-server-models-list">${modelsList}</div>
        </div>
    `;
    
    return card;
}

// Create server table row for desktop view
function createServerTableRow(url, config) {
    const models = Object.entries(config.model || {}).map(([k, v]) => {
        const statusClass = v.status ? 'text-green-500' : 'text-red-500';
        const statusIcon = v.status ? 'fa-check-circle' : 'fa-times-circle';
        const statusTitle = v.status ? 'Active' : 'Inactive';
        const statusClick = `toggleModelStatus('${encodeURIComponent(url)}','${encodeURIComponent(k)}',${v.status})`;
        return [
            '<div class="flex items-center justify-between py-1">',
            '<span>' + k + '</span>',
            '<div class="flex items-center space-x-2">',
            '<span class="text-xs text-gray-500">' + v.reqs.toString() + ' reqs</span>',
            '<i class="fas ' + statusIcon + ' ' + statusClass + '" title="' + statusTitle.toString() + '" onclick="' + statusClick + '"></i>',
            '</div>',
            '</div>'
        ].join('');
    }).join('');
    
    const row = document.createElement('tr');
    row.className = 'hover:bg-gray-50 transition-colors';
    row.innerHTML = '<td class="px-2 md:px-4 py-2 md:py-3 text-xs md:text-sm text-gray-700">' + url + '</td>' +
        '<td class="px-2 md:px-4 py-2 md:py-3 text-xs md:text-sm text-gray-700">' + (config.device || 'N/A') + '</td>' +
        '<td class="px-2 md:px-4 py-2 md:py-3 text-xs md:text-sm text-gray-700">' +
        '<div class="flex items-center">' +
        '<span class="font-mono text-xs bg-gray-100 px-2 py-1 rounded border break-all max-w-xs">' + (config.apikey || 'No API Key') + '</span>' +
        (config.apikey ? '<button onclick="copyToClipboard(\'' + config.apikey + '\')" class="ml-2 text-gray-400 hover:text-indigo-600 transition-colors" title="Copy API Key"><i class="fas fa-copy text-xs"></i></button>' : '') +
        '</div></td>' +
        '<td class="px-2 md:px-4 py-2 md:py-3 text-xs md:text-sm text-gray-700"><div class="space-y-1">' + models + '</div></td>' +
        '<td class="px-2 md:px-4 py-2 md:py-3 text-xs md:text-sm space-x-2">' +
        '<button onclick="showEditServerModal(\'' + encodeURIComponent(url) + '\')" class="text-indigo-600 hover:text-indigo-800" title="Edit">' +
        '<i class="fas fa-edit"></i></button>' +
        '<button onclick="deleteServer(\'' + encodeURIComponent(url) + '\')" class="text-red-600 hover:text-red-800" title="Delete">' +
        '<i class="fas fa-trash"></i></button></td>';
    
    return row;
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

    // Collect models from table
    const models = {};
    const rows = document.querySelectorAll('#addServerModelsTable tr');
    
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
            models[frontendModel] = {
                name: backendModel,
                status: status,
                reqs: 0,
                input_token_weight: inputWeight,
                output_token_weight: outputWeight
            };
        }
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
            throw new Error('Failed to add server');
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
                   value="${frontendModel}" placeholder="Frontend model name">
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
    addModelRow('', '', true, 0, target);
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

    // Collect models from table
    const models = {};
    const rows = document.querySelectorAll('#editServerModelsTable tr');
    
    // Get current server data once to avoid multiple API calls
    let currentServerData = null;
    try {
        const serversResponse = await fetch('/get-llm-servers');
        const servers = await serversResponse.json();
        currentServerData = servers[oldUrl];
    } catch (error) {
        console.warn('Could not fetch current server data:', error);
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

        console.log('Update successful');
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
document.addEventListener('DOMContentLoaded', function() {
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

        // Update the limit text
        document.getElementById(`limit_${apiKey}`).textContent = newLimit;
        
        // Find the corresponding progress bar and update it
        const row = document.querySelector(`[data-key="${apiKey}"]`).closest('tr');
        if (row) {
            const usageCell = row.querySelector('td:nth-child(3)');
            const usageSpan = usageCell.querySelector('span');
            const usageText = usageSpan.textContent;
            const currentUsage = parseInt(usageText.split('/')[0]);
            
            // Update the usage text label
            usageSpan.textContent = `${currentUsage}/${newLimit}`;
            
            // Update the progress bar data attributes
            const progressBar = usageCell.querySelector('.api-key-usage');
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

    // Show loading state
    const button = container.querySelector('button');
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Loading...';
    button.disabled = true;

    try {
        // Fetch actual model usage data from the server
        const response = await fetch('/get-usage');
        if (!response.ok) {
            throw new Error('Failed to fetch usage data');
        }

        const html = await response.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');

        // Find the specific API key row in the parsed HTML
        const apiKeyRow = doc.querySelector(`.model-usage-container[data-key="${apiKey}"]`)?.closest('tr');
        if (!apiKeyRow) {
            throw new Error('API key data not found');
        }

        // Extract model usage data from the row
        const modelUsageCell = apiKeyRow.querySelector('td:nth-child(6)');
        if (!modelUsageCell) {
            throw new Error('Model usage cell not found');
        }

        // Check if there are models available
        const buttonText = modelUsageCell.textContent;
        const modelCountMatch = buttonText.match(/\((\d+) models\)/);
        if (!modelCountMatch || parseInt(modelCountMatch[1]) === 0) {
            console.log('No model usage data found for API key:', apiKey);
            button.innerHTML = originalText;
            button.disabled = false;
            return;
        }

        // Get the actual model usage data from the page data
        const apiKeysDataElement = document.getElementById('apiKeysData');
        if (!apiKeysDataElement) {
            throw new Error('API keys data element not found');
        }

        const apiKeys = JSON.parse(apiKeysDataElement.textContent);
        const currentKey = apiKeys.find(key => key.key === apiKey);

        if (!currentKey || !currentKey.model_usage) {
            console.log('No model usage data found for API key:', apiKey);
            button.innerHTML = originalText;
            button.disabled = false;
            return;
        }

        const details = createModelUsageDetails(currentKey.model_usage);
        container.appendChild(details);

    } catch (error) {
        console.error('Error loading model usage data:', error);
        // Fallback to placeholder data
        const placeholderModelUsage = {
            "default-model": {
                "requests": 15,
                "tokens": 2500
            }
        };
        const details = createModelUsageDetails(placeholderModelUsage);
        container.appendChild(details);
    } finally {
        // Restore button state
        button.innerHTML = originalText;
        button.disabled = false;
    }
}

function createModelUsageDetails(modelUsage) {
    const details = document.createElement('div');
    details.className = 'model-usage-details mt-3 p-4 bg-gray-50 rounded-lg border border-gray-200';

    const table = document.createElement('table');
    table.className = 'w-full text-sm';

    const header = document.createElement('thead');
    header.innerHTML = `
        <tr class="bg-gray-100">
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Model</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Requests</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tokens</th>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Avg Tokens/Req</th>
        </tr>
    `;

    const body = document.createElement('tbody');
    body.className = 'bg-white divide-y divide-gray-200';

    Object.entries(modelUsage).forEach(([model, usage]) => {
        const row = document.createElement('tr');
        const avgTokens = usage.requests > 0 ? (usage.tokens / usage.requests).toFixed(1) : '0';

        row.innerHTML = `
            <td class="px-3 py-2 whitespace-nowrap text-sm font-medium text-gray-900">${model}</td>
            <td class="px-3 py-2 whitespace-nowrap text-sm text-gray-500">${usage.requests}</td>
            <td class="px-3 py-2 whitespace-nowrap text-sm text-gray-500">${usage.tokens.toFixed(0)}</td>
            <td class="px-3 py-2 whitespace-nowrap text-sm text-gray-500">${avgTokens}</td>
        `;
        body.appendChild(row);
    });

    table.appendChild(header);
    table.appendChild(body);
    details.appendChild(table);

    return details;
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
