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
    const url = `https://ldoce.onlyquant.top/word/${selectedText}`;

    chrome.tabs.create({
      url: url
    });
  }
});