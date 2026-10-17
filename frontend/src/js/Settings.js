import { createIcons, icons } from "lucide";
import { safeUrl } from "../shared/format.js";
import { getSettings, updateSettings } from "../js/inventory/services/inventory-api";

let selectedLogoFile = null;

window.initializeSettings = async function() {
    await loadSettings();
    createIcons({ icons });
};

async function loadSettings() {
    try {
        const response = await getSettings();
        if (response) {
            populateForm(response);
        }
    } catch (error) {
        console.error("Failed to load settings:", error);
        showToast(error?.message ? `Error loading settings: ${error.message}` : "Error loading settings", "error");
    }
}

function populateForm(data) {
    const fields = [
        "company_name", "tagline", "address", "phone", "email", 
        "website", "tax_number", "gst_number", "currency", 
        "receipt_paper_size", "receipt_footer"
    ];
    
    fields.forEach(field => {
        const el = document.getElementById(`setting-${field}`);
        if (el && data[field] !== undefined) {
            el.value = data[field];
        }
    });
    
    // Only server-provided http(s)/relative URLs; a locally chosen file still previews via its data: URL.
    const logoUrl = safeUrl(data.logo_url);
    if (logoUrl) {
        showLogoPreview(logoUrl);
    }
}

window.previewLogo = function(event) {
    const file = event.target.files[0];
    if (file) {
        selectedLogoFile = file;
        const reader = new FileReader();
        reader.onload = function(e) {
            showLogoPreview(e.target.result);
        };
        reader.readAsDataURL(file);
    }
};

function showLogoPreview(src) {
    const preview = document.getElementById("setting-logo-preview");
    const placeholder = document.getElementById("setting-logo-placeholder");
    
    if (preview && placeholder) {
        preview.src = src;
        preview.classList.remove("hidden");
        placeholder.classList.add("hidden");
    }
}

let savingSettings = false;

window.saveSettings = async function() {
    if (savingSettings) return;
    savingSettings = true;
    try {
        const formData = new FormData();
        
        const fields = [
            "company_name", "tagline", "address", "phone", "email", 
            "website", "tax_number", "gst_number", "currency", 
            "receipt_paper_size", "receipt_footer"
        ];
        
        fields.forEach(field => {
            const el = document.getElementById(`setting-${field}`);
            if (el) {
                formData.append(field, el.value);
            }
        });
        
        if (selectedLogoFile) {
            formData.append("logo", selectedLogoFile);
        }
        
        await updateSettings(formData);
        selectedLogoFile = null;
        showToast("Settings saved successfully!", "success");
        // Let the sidebar refresh its cached company profile (name/logo).
        window.dispatchEvent(new CustomEvent("company:updated"));
    } catch (error) {
        console.error("Failed to save settings:", error);
        // Show the backend's validation/permission message instead of a generic one.
        showToast(error?.message ? `Could not save settings: ${error.message}` : "Error saving settings", "error");
    } finally {
        savingSettings = false;
    }
};

function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `fixed bottom-6 right-6 px-6 py-3 rounded-xl shadow-xl text-white font-medium z-50 transition-opacity duration-300 ${type === 'success' ? 'bg-emerald-600' : 'bg-red-600'}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
