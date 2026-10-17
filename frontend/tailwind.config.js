/** @type {import('tailwindcss').Config} */
module.exports = {
  // html.dark (src/shared/theme.js) enables dark: variants; the shared palette
  // is remapped in src/styles/dark-theme.css.
  darkMode: "class",

  content: [
    "./index.html",
    "./receipt.html",
    "./src/**/*.{html,js}",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{html,js}",
    "./pages/**/*.{html,js}",
    "./*.js",
  ],

  theme: {
    screens: {
      mmd: "992px",
    },

    extend: {
      colors: {
        sidebar: {
          bg: "#141922",
          card: "#1b212c",
          border: "#242b37",
        },

        accent: {
          DEFAULT: "#a3e635",
          dim: "rgba(163, 230, 53, 0.12)",
        },
      },
    },
  },

  plugins: [],
};
