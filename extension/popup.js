document.addEventListener('DOMContentLoaded', async function() {
    const saveBtn = document.getElementById('saveBtn');
    const statusDiv = document.getElementById('status');
    
    // Check if settings are configured
    const settings = await chrome.storage.sync.get(['serverUrl', 'username', 'password']);
    
    if (!settings.serverUrl || !settings.username || !settings.password) {
        saveBtn.disabled = true;
        statusDiv.innerHTML = 'Please <a href="#" class="setup-link">configure settings</a> first.';
        statusDiv.className = 'error';
        
        document.querySelector('.setup-link').addEventListener('click', function(e) {
            e.preventDefault();
            chrome.runtime.openOptionsPage();
        });
        return;
    }
    
    saveBtn.addEventListener('click', async function() {
        saveBtn.disabled = true;
        statusDiv.textContent = 'Saving...';
        statusDiv.className = '';
        
        try {
            // Get current tab URL
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            const url = tab.url;
            
            // Call API
            const response = await fetch(settings.serverUrl + '/api/articles', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Basic ' + btoa(settings.username + ':' + settings.password)
                },
                body: JSON.stringify({ url: url })
            });
            
            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
                throw new Error(error.detail || 'Failed to save article');
            }
            
            const article = await response.json();
            statusDiv.textContent = 'Saved: ' + article.title;
            statusDiv.className = 'success';
            
        } catch (error) {
            statusDiv.textContent = 'Error: ' + error.message;
            statusDiv.className = 'error';
        } finally {
            saveBtn.disabled = false;
        }
    });
});
