document.addEventListener('DOMContentLoaded', function () {
  const urlInput = document.getElementById('dictionaryUrl');
  const saveButton = document.getElementById('saveButton');
  const statusDiv = document.getElementById('status');

  // Load saved settings
  chrome.storage.sync.get(['dictionaryUrl'], function (result) {
    if (result.dictionaryUrl) {
      urlInput.value = result.dictionaryUrl;
    } else {
      // Set default value
      urlInput.value = 'https://www.ldoceonline.com/dictionary/{word}';
    }
  });

  // Save settings
  saveButton.addEventListener('click', function () {
    const url = urlInput.value.trim();

    if (!url) {
      showStatus('Please enter a valid URL', 'error');
      return;
    }

    if (!url.includes('{word}')) {
      showStatus('URL must include {word} placeholder', 'error');
      return;
    }

    chrome.storage.sync.set({ dictionaryUrl: url }, function () {
      showStatus('Settings saved successfully!', 'success');
    });
  });

  function showStatus(message, type) {
    statusDiv.textContent = message;
    statusDiv.className = 'status ' + type;
    statusDiv.style.display = 'block';

    setTimeout(function () {
      statusDiv.style.display = 'none';
    }, 3000);
  }
});
