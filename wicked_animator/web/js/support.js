// "Buy me a coffee": the tip page. The button shows only once this is set (the page must be yours: never guess a name).
export const SUPPORT_URL = 'https://www.buymeacoffee.com/novulon';
// Novulon's site: both apps and every other project
export const SITE_URL = 'https://novulon.pages.dev';
export const hasSupport = () => /^https:\/\//.test(SUPPORT_URL);
