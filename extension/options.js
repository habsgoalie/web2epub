document.addEventListener('DOMContentLoaded', async function() {
    const form = document.getElementById('settingsForm');
    const serverUrlInput = document.getElementById('serverUrl');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const testBtn = document.getElementById('testBtn');
    const statusDiv = document.getElementById('status');
    
    // Load existing settings
    const settings = await chrome.storage.sync.get(['serverUrl', 'username', 'password']);
    if (settings.serverUrl) serverUrlInput.value = settings.serverUrl;
    if (settings.username) usernameInput.value = settings.username;
    if (settings.password) passwordInput.value = settings.password;
    
    // Save settings
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const serverUrl = serverUrlInput.value.replace(/\/$/, ''); // Remove trailing slash
        const username = usernameInput.value;
        const password = passwordInput.value;
        
        await chrome.storage.sync.set({
            serverUrl: serverUrl,
            username: username,
            password: password
        });
        
        showStatus('Settings saved!', 'success');
    });
    
    // Test connection
    testBtn.addEventListener('click', async function() {
        const serverUrl = serverUrlInput.value.replace(/\/$/, '');
        const username = usernameInput.value;
        const password = passwordInput.value;
        
        if (!serverUrl || !username || !password) {
            showStatus('Please fill in all fields first', 'error');
            return;
        }
        
        testBtn.disabled = true;
        testBtn.textContent = 'Testing...';
        
        try {
            const response = await fetch(serverUrl + '/api/articles', {
                method: 'GET',
                headers: {
                    'Authorization': 'Basic ' + btoa(username + ':' + password)
                }
            });
            
            if (response.ok) {
                showStatus('Connection successful!', 'success');
            } else if (response.status === 401) {
                showStatus('Authentication failed. Check your username and password.', 'error');
            } else {
                showStatus('Connection failed: ' + response.status + ' ' + response.statusText, 'error');
            }
        } catch (error) {
            showStatus('Connection failed: ' + error.message, 'error');
        } finally {
            testBtn.disabled = false;
            testBtn.textContent = 'Test Connection';
        }
    });
    
    function showStatus(message, type) {
        statusDiv.textContent = message;
        statusDiv.className = type;
        
        // Hide after 5 seconds if success
        if (type === 'success') {
            setTimeout(() => {
                statusDiv.className = '';
            }, 5000);
        }
    }
});
