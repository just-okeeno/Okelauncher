// ChromeOverlayBridge.hpp
// Win32 + UI Automation + JSON/File helpers to control Chrome from a custom overlay.
// Link with: ole32.lib oleaut32.lib user32.lib shell32.lib

#pragma once
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

#include <windows.h>
#include <uiautomation.h>
#include <shellapi.h>
#include <wrl/client.h>
#include <string>
#include <fstream>
#include <sstream>

using Microsoft::WRL::ComPtr;

class ChromeOverlayBridge {
public:
    bool Init() {
        HRESULT hr = CoCreateInstance(
            CLSID_CUIAutomation, nullptr, CLSCTX_INPROC_SERVER,
            IID_PPV_ARGS(&m_uia));
        return SUCCEEDED(hr) && m_uia != nullptr;
    }

    // Find top-level Chrome window
    HWND FindChromeWindow() const {
        HWND hwnd = nullptr;
        while ((hwnd = FindWindowExW(nullptr, hwnd, L"Chrome_WidgetWin_1", nullptr)) != nullptr) {
            if (IsWindowVisible(hwnd)) {
                return hwnd;
            }
        }
        return nullptr;
    }

    // Position your custom overlay bar (e.g., 56px top bar) aligned to Chrome's client/window rect
    void SyncOverlayToChrome(HWND overlayHwnd, int topBarHeightPx) {
        HWND chrome = FindChromeWindow();
        if (!chrome || !overlayHwnd) return;

        RECT rc = {};
        if (GetWindowRect(chrome, &rc)) {
            int w = rc.right - rc.left;
            SetWindowPos(
                overlayHwnd,
                HWND_TOPMOST,
                rc.left,
                rc.top,
                w,
                topBarHeightPx,
                SWP_NOACTIVATE | SWP_SHOWWINDOW
            );
        }
    }

    // 1) Trigger Chrome "Back" from your custom Back button
    bool NavigateBack() {
        HWND chrome = FindChromeWindow();
        if (!chrome) return false;

        // Method A: UI Automation invoke on "Back" button if accessible
        if (m_uia) {
            ComPtr<IUIAutomationElement> root;
            if (SUCCEEDED(m_uia->ElementFromHandle(chrome, &root)) && root) {
                VARIANT propVal{};
                VariantInit(&propVal);
                propVal.vt = VT_BSTR;
                propVal.bstrVal = SysAllocString(L"Back");
                if (propVal.bstrVal) {
                    ComPtr<IUIAutomationCondition> cond;
                    if (SUCCEEDED(m_uia->CreatePropertyCondition(UIA_NamePropertyId, propVal, &cond)) && cond) {
                        ComPtr<IUIAutomationElement> backBtn;
                        if (SUCCEEDED(root->FindFirst(TreeScope_Descendants, cond.Get(), &backBtn)) && backBtn) {
                            ComPtr<IUIAutomationInvokePattern> invoke;
                            if (SUCCEEDED(backBtn->GetCurrentPatternAs(UIA_InvokePatternId, IID_PPV_ARGS(&invoke))) && invoke) {
                                if (SUCCEEDED(invoke->Invoke())) {
                                    VariantClear(&propVal);
                                    return true;
                                }
                            }
                        }
                    }
                    VariantClear(&propVal);
                }
            }
        }

        // Method B: Reliable fallback via WM_APPCOMMAND / VK_BROWSER_BACK
        SendMessageW(chrome, WM_APPCOMMAND, (WPARAM)chrome,
                     MAKELPARAM(0, APPCOMMAND_BROWSER_BACKWARD));
        return true;
    }

    // Trigger Chrome "Forward"
    bool NavigateForward() {
        HWND chrome = FindChromeWindow();
        if (!chrome) return false;
        SendMessageW(chrome, WM_APPCOMMAND, (WPARAM)chrome,
                     MAKELPARAM(0, APPCOMMAND_BROWSER_FORWARD));
        return true;
    }

    // Trigger Chrome "Reload"
    bool ReloadPage() {
        HWND chrome = FindChromeWindow();
        if (!chrome) return false;
        SendMessageW(chrome, WM_APPCOMMAND, (WPARAM)chrome,
                     MAKELPARAM(0, APPCOMMAND_BROWSER_REFRESH));
        return true;
    }

    // 2) Change Chrome language (e.g., "es" for Spanish) from your custom Settings UI
    //    Note: Chrome must be closed for this change to persist; takes effect on next launch.
    bool SetChromeLanguage(const std::wstring& langCode /* e.g. L"es" */) {
        std::wstring localStatePath = GetChromeLocalStatePath();
        if (localStatePath.empty()) return false;

        std::string narrowLang = WideToUtf8(langCode);
        std::string content = ReadFileUtf8(localStatePath);
        if (content.empty()) return false;

        // Update or insert "intl":{"app_locale":"es"} in Local State JSON
        std::string key = "\"app_locale\"";
        size_t pos = content.find(key);
        if (pos != std::string::npos) {
            size_t colon = content.find(':', pos + key.size());
            size_t q1 = (colon != std::string::npos) ? content.find('"', colon + 1) : std::string::npos;
            size_t q2 = (q1 != std::string::npos) ? content.find('"', q1 + 1) : std::string::npos;
            if (q1 != std::string::npos && q2 != std::string::npos) {
                content.replace(q1 + 1, q2 - q1 - 1, narrowLang);
            }
        } else {
            // Inject inside top-level '{' if app_locale isn't present yet
            size_t brace = content.find('{');
            if (brace != std::string::npos) {
                std::string inject = "\"intl\":{\"app_locale\":\"" + narrowLang + "\"},";
                content.insert(brace + 1, inject);
            }
        }

        return WriteFileUtf8(localStatePath, content);
    }

    // Launch Chrome with a specific UI language flag (e.g., --lang=es)
    bool LaunchChromeWithLang(const std::wstring& langCode, const std::wstring& url = L"") {
        std::wstring chromeExe = FindChromeExePath();
        if (chromeExe.empty()) return false;

        std::wstring args = L"--lang=" + langCode;
        if (!url.empty()) {
            args += L" \"" + url + L"\"";
        }

        SHELLEXECUTEINFOW sei = {};
        sei.cbSize = sizeof(sei);
        sei.lpVerb = L"open";
        sei.lpFile = chromeExe.c_str();
        sei.lpParameters = args.c_str();
        sei.nShow = SW_SHOWNORMAL;
        return ShellExecuteExW(&sei) != FALSE;
    }

private:
    ComPtr<IUIAutomation> m_uia;

    static std::wstring GetChromeLocalStatePath() {
        wchar_t localAppData[MAX_PATH] = {};
        if (GetEnvironmentVariableW(L"LOCALAPPDATA", localAppData, MAX_PATH) == 0)
            return L"";
        return std::wstring(localAppData) + L"\\Google\\Chrome\\User Data\\Local State";
    }

    static std::wstring FindChromeExePath() {
        const wchar_t* candidates[] = {
            L"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            L"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
        };
        for (const wchar_t* p : candidates) {
            DWORD attr = GetFileAttributesW(p);
            if (attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY))
                return p;
        }
        wchar_t localAppData[MAX_PATH] = {};
        if (GetEnvironmentVariableW(L"LOCALAPPDATA", localAppData, MAX_PATH) > 0) {
            std::wstring p = std::wstring(localAppData) + L"\\Google\\Chrome\\Application\\chrome.exe";
            if (GetFileAttributesW(p.c_str()) != INVALID_FILE_ATTRIBUTES)
                return p;
        }
        return L"chrome.exe";
    }

    static std::string WideToUtf8(const std::wstring& w) {
        if (w.empty()) return {};
        int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), nullptr, 0, nullptr, nullptr);
        std::string out(n, 0);
        WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), out.data(), n, nullptr, nullptr);
        return out;
    }

    static std::string ReadFileUtf8(const std::wstring& path) {
        std::ifstream ifs(path, std::ios::binary);
        if (!ifs) return {};
        std::ostringstream oss;
        oss << ifs.rdbuf();
        return oss.str();
    }

    static bool WriteFileUtf8(const std::wstring& path, const std::string& data) {
        std::ofstream ofs(path, std::ios::binary | std::ios::trunc);
        if (!ofs) return false;
        ofs.write(data.data(), (std::streamsize)data.size());
        return ofs.good();
    }
};
