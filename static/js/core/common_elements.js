import { $ } from "./dom.js";

export function getCommonElements() {
  return {
    statusMessage: $("#statusMessage"),
    languageSelect: $("#languageSelect"),

    toggleSidebarButton: $("#toggleSidebarButton"),
    toggleViewerSidebarButton: $("#toggleViewerSidebarButton"),

    backToGalleryButton: $("#backToGalleryButton"),

    dialogOverlay: $("#dialogOverlay"),
    dialogTitle: $("#dialogTitle"),
    dialogMessage: $("#dialogMessage"),
    dialogConfirmButton: $("#dialogConfirmButton"),
    dialogCancelButton: $("#dialogCancelButton"),
  };
}