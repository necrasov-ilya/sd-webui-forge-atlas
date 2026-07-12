function atlasSelectTopLevelTab(panelId) {
    const tabs = gradioApp().getElementById("tabs");
    const panels = Array.from(tabs.querySelectorAll(":scope > .tabitem"));
    const buttons = Array.from(tabs.querySelectorAll(":scope > .tab-nav > button"));
    const index = panels.findIndex((panel) => panel.id === panelId);
    if (index >= 0 && buttons[index]) buttons[index].click();
}

function atlasSelectImproveMode(index) {
    atlasSelectTopLevelTab("tab_upscale");
    const modes = gradioApp().getElementById("atlas_improve_modes");
    modes?.querySelectorAll(":scope > .tab-nav > button")[index]?.click();
}

function atlasAutosizeTextarea(textarea) {
    if (!textarea || textarea.dataset.atlasAutosize === "true") return;
    textarea.dataset.atlasAutosize = "true";
    const resize = () => {
        textarea.style.height = "auto";
        textarea.style.height = `${Math.min(Math.max(textarea.scrollHeight, 96), 420)}px`;
    };
    textarea.addEventListener("input", resize);
    resize();
}

onAfterUiUpdate(() => {
    gradioApp()
        .querySelectorAll(".atlas-autogrow textarea")
        .forEach(atlasAutosizeTextarea);
});
