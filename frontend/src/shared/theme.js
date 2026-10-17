/**
 * Light/dark theme. The preference is stored per browser under "pos-theme";
 * html.dark activates src/styles/dark-theme.css (overrides of the shared light
 * palette) and Tailwind's dark: variants (darkMode: "class"). Applied before
 * the first render so every screen, including login, starts in the right theme.
 */
const STORAGE_KEY = "pos-theme";

export function isDarkMode() {
    try {
        return localStorage.getItem(STORAGE_KEY) === "dark";
    } catch {
        return false;
    }
}

export function applyTheme(dark = isDarkMode(), root = document.documentElement) {
    root.classList.toggle("dark", Boolean(dark));
    root.style.colorScheme = dark ? "dark" : "light";
    return Boolean(dark);
}

export function setDarkMode(dark) {
    try {
        localStorage.setItem(STORAGE_KEY, dark ? "dark" : "light");
    } catch {
        // Storage unavailable (private mode): the theme still applies for this page.
    }
    return applyTheme(dark);
}

export function toggleDarkMode() {
    return setDarkMode(!isDarkMode());
}
