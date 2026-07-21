/**
 * OS-aware download CTA for Donna GitHub Releases.
 */
(function () {
  "use strict";

  var RELEASES_LATEST =
    "https://github.com/Cascade-Router/Donna/releases/latest";
  var DOWNLOAD_BASE =
    "https://github.com/Cascade-Router/Donna/releases/latest/download";

  // Filenames must match softprops upload list in .github/workflows/release.yml
  var ASSETS = {
    windows: {
      label: "Download for Windows",
      href: DOWNLOAD_BASE + "/Donna-windows-x64.zip",
    },
    macos: {
      label: "Download for Mac",
      href: DOWNLOAD_BASE + "/Donna-macos-x64.dmg",
    },
    linux: {
      label: "Download for Linux",
      href: DOWNLOAD_BASE + "/Donna-linux-x86_64.AppImage",
    },
    fallback: {
      label: "View Releases",
      href: RELEASES_LATEST,
    },
  };

  /**
   * @param {string} ua
   * @returns {"windows"|"macos"|"linux"|"unknown"}
   */
  function detectOs(ua) {
    var value = String(ua || "").toLowerCase();
    // iPadOS 13+ may report as Macintosh — treat touch Macs as macOS for DMG.
    if (/windows|win32|win64|wow64/.test(value)) {
      return "windows";
    }
    if (/android/.test(value)) {
      return "unknown";
    }
    if (/iphone|ipad|ipod/.test(value)) {
      return "unknown";
    }
    if (/mac os x|macintosh|mac_powerpc/.test(value)) {
      return "macos";
    }
    if (/linux|x11|cros/.test(value)) {
      return "linux";
    }
    return "unknown";
  }

  function applyDownloadButton() {
    var btn = document.getElementById("download-btn");
    if (!btn) {
      return;
    }

    var os = detectOs(navigator.userAgent || "");
    var asset =
      os === "windows"
        ? ASSETS.windows
        : os === "macos"
          ? ASSETS.macos
          : os === "linux"
            ? ASSETS.linux
            : ASSETS.fallback;

    btn.textContent = asset.label;
    btn.setAttribute("href", asset.href);
    btn.dataset.os = os;

    var hint = document.getElementById("os-hint");
    if (hint) {
      if (os === "unknown") {
        hint.textContent = "OS not detected — opening the GitHub Releases page.";
      } else {
        hint.textContent = "Detected " + os + " — serving the matching installer.";
      }
    }
  }

  // Expose for manual verification / tests.
  window.DonnaLanding = {
    detectOs: detectOs,
    applyDownloadButton: applyDownloadButton,
    ASSETS: ASSETS,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyDownloadButton);
  } else {
    applyDownloadButton();
  }
})();
