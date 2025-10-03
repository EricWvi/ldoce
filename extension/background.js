// Create context menu item
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "lookupWord",
    title: 'Look up "%s"',
    contexts: ["selection"]
  });
});

// Handle context menu click
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "lookupWord") {
    const selectedText = info.selectionText.trim().toLowerCase();

    // Get the configured URL from storage
    chrome.storage.sync.get(['dictionaryUrl'], function (result) {
      let urlTemplate = result.dictionaryUrl || 'https://www.ldoceonline.com/dictionary/{word}';
      const url = urlTemplate.replace('{word}', selectedText);

      chrome.tabs.create({
        url: url
      });
    });
  }
});
