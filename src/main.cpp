// Oke Launcher — futuristic minimal movie / TV launcher
// Win32 + Direct2D + DirectWrite + WIC. No external dependencies.

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <windowsx.h>
#include <d2d1.h>
#include <dwrite.h>
#include <wincodec.h>
#include <dwmapi.h>
#include <shellapi.h>
#include <wrl/client.h>
#include <string>
#include <vector>
#include <algorithm>
#include <cstdint>
#include <map>
#include <set>
#include <cwctype>
#include <cstdio>

#ifndef DWMWA_WINDOW_CORNER_PREFERENCE
#define DWMWA_WINDOW_CORNER_PREFERENCE 33
#endif
#ifndef DWMWA_USE_IMMERSIVE_DARK_MODE
#define DWMWA_USE_IMMERSIVE_DARK_MODE 20
#endif

using Microsoft::WRL::ComPtr;

// ---------------------------------------------------------------- palette
namespace theme {
    static const D2D1_COLOR_F Background = { 0.035f, 0.047f, 0.070f, 1.0f };
    static const D2D1_COLOR_F Text      = { 0.902f, 0.937f, 0.973f, 1.0f };
    static const D2D1_COLOR_F TextDim   = { 0.420f, 0.465f, 0.522f, 1.0f };
    static const D2D1_COLOR_F TextMid   = { 0.640f, 0.690f, 0.745f, 1.0f };
    static const D2D1_COLOR_F Accent    = { 0.180f, 0.795f, 0.950f, 1.0f };
    static const D2D1_COLOR_F Hairline  = { 0.180f, 0.795f, 0.950f, 0.22f };
}

// ---------------------------------------------------------------- helpers
static std::wstring ToLower(std::wstring s) {
    std::transform(s.begin(), s.end(), s.begin(), ::towlower);
    return s;
}
static std::wstring Trim(const std::wstring& s) {
    size_t a = s.find_first_not_of(L" \t\r\n");
    if (a == std::wstring::npos) return L"";
    size_t b = s.find_last_not_of(L" \t\r\n");
    return s.substr(a, b - a + 1);
}
static std::wstring DirName(const std::wstring& path) {
    size_t p = path.find_last_of(L"\\/");
    return (p == std::wstring::npos) ? L"" : path.substr(0, p);
}
static std::wstring FileName(const std::wstring& path) {
    size_t p = path.find_last_of(L"\\/");
    return (p == std::wstring::npos) ? path : path.substr(p + 1);
}
static std::wstring ExtOf(const std::wstring& path) {
    std::wstring f = FileName(path);
    size_t p = f.find_last_of(L'.');
    return (p == std::wstring::npos) ? L"" : ToLower(f.substr(p + 1));
}
static std::wstring StemOf(const std::wstring& path) {
    std::wstring f = FileName(path);
    size_t p = f.find_last_of(L'.');
    if (p != std::wstring::npos) f = f.substr(0, p);
    return f;
}

static bool IsVideoPath(const std::wstring& path) {
    static const wchar_t* exts[] = {
        L"mp4", L"mkv", L"avi", L"mov", L"m4v", L"wmv",
        L"flv", L"webm", L"mpg", L"mpeg", L"ts", L"m2ts"
    };
    std::wstring e = ExtOf(path);
    for (const wchar_t* x : exts) if (e == x) return true;
    return false;
}

// "Movie.Name.2023" -> "Movie Name 2023", removing [tag] and (tag) groups
static std::wstring PrettifyTitle(std::wstring t) {
    const wchar_t* pairs[][2] = { { L"[", L"]" }, { L"(", L")" } };
    for (auto& pv : pairs) {
        size_t r;
        while ((r = t.find(pv[0])) != std::wstring::npos) {
            size_t e = t.find(pv[1], r + 1);
            if (e == std::wstring::npos) { t = t.substr(0, r); break; }
            t.erase(r, e - r + 1);
        }
    }
    for (wchar_t& c : t) if (c == L'.' || c == L'_') c = L' ';
    t = Trim(t);
    std::wstring out;                          // collapse runs of spaces
    for (wchar_t c : t) {
        if (c == L' ' && !out.empty() && out.back() == L' ') continue;
        out += c;
    }
    if (out.size() > 64) out = out.substr(0, 64) + L"\x2026";
    return out;
}

static std::wstring DisplayDirName(const std::wstring& path) {
    std::wstring d = FileName(DirName(path));
    if (d.empty()) return L"";
    if (_wcsnicmp(d.c_str(), L"season", 6) == 0)
        return FileName(DirName(DirName(path)));   // show name above "Season x"
    return d;
}

static std::wstring FindPosterPath(const std::wstring& video) {
    static const wchar_t* names[] = {
        L"poster.jpg", L"poster.png", L"folder.jpg", L"folder.png",
        L"cover.jpg", L"cover.png", L"art.jpg", L"art.png"
    };
    std::wstring dirs[2] = { DirName(video), DirName(DirName(video)) };
    for (const std::wstring& dir : dirs) {
        for (const wchar_t* n : names) {
            std::wstring p = dir + L"\\" + n;
            DWORD a = GetFileAttributesW(p.c_str());
            if (a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY))
                return p;
        }
        if (dir.empty()) break;
    }
    return L"";
}

// ---------------------------------------------------------------- scanning
struct MediaItem {
    std::wstring path;      // full path to video
    std::wstring title;     // display title
    std::wstring sub;       // subtitle (library / show)
    std::wstring poster;    // poster image path (may be empty)
};

static void ScanDirectory(const std::wstring& dir, int depth, int maxDepth,
                          const std::wstring& libLabel, std::vector<MediaItem>& out) {
    if (depth > maxDepth) return;
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW((dir + L"\\*").c_str(), &fd);
    if (h == INVALID_HANDLE_VALUE) return;
    do {
        if (fd.cFileName[0] == L'.') continue;
        std::wstring full = dir + L"\\" + fd.cFileName;
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            ScanDirectory(full, depth + 1, maxDepth, libLabel, out);
        } else if (IsVideoPath(full)) {
            std::wstring stem = ToLower(FileName(full));
            if (stem.rfind(L"sample", 0) == 0 || stem.rfind(L"trailer", 0) == 0)
                continue;
            MediaItem it;
            it.path = full;
            it.title = PrettifyTitle(StemOf(full));
            it.sub = DisplayDirName(full);
            if (_wcsicmp(it.sub.c_str(), libLabel.c_str()) == 0) it.sub.clear();
            it.poster = FindPosterPath(full);
            out.push_back(std::move(it));
        }
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}

// ---------------------------------------------------------------- config
static std::string WideToUtf8(const std::wstring& w) {
    if (w.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(),
                                nullptr, 0, nullptr, nullptr);
    std::string s(n, 0);
    WideCharToMultiByte(CP_UTF8, 0, w.c_str(), (int)w.size(), s.data(), n, nullptr, nullptr);
    return s;
}
static std::wstring Utf8ToWide(const std::string& u) {
    if (u.empty()) return {};
    int n = MultiByteToWideChar(CP_UTF8, 0, u.c_str(), (int)u.size(), nullptr, 0);
    std::wstring w(n, 0);
    MultiByteToWideChar(CP_UTF8, 0, u.c_str(), (int)u.size(), w.data(), n);
    return w;
}

static std::wstring ConfigPath() {
    wchar_t buf[MAX_PATH];
    std::wstring base;
    DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", buf, MAX_PATH);
    if (n > 0 && n < MAX_PATH) base = buf;
    if (base.empty()) base = L".";
    std::wstring dir = base + L"\\OkeLauncher";
    CreateDirectoryW(dir.c_str(), nullptr);
    return dir + L"\\oke.cfg";
}

static std::vector<std::wstring> ReadLibraries() {
    std::vector<std::wstring> libs;
    HANDLE f = CreateFileW(ConfigPath().c_str(), GENERIC_READ, FILE_SHARE_READ,
                           nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return libs;
    char buf[16384] = {};
    DWORD got = 0;
    ReadFile(f, buf, sizeof(buf) - 1, &got, nullptr);
    CloseHandle(f);
    std::string data(buf, got);
    size_t pos = 0;
    while (pos < data.size()) {
        size_t e = data.find('\n', pos);
        std::string line = data.substr(pos, (e == std::string::npos ? data.size() : e) - pos);
        pos = (e == std::wstring::npos) ? data.size() : e + 1;
        std::wstring w = Utf8ToWide(Trim(line));
        if (w.rfind(L"libraries=", 0) == 0) w = w.substr(10);
        w = Trim(w);
        if (w.empty()) continue;
        size_t a = 0;
        while (a <= w.size()) {
            size_t b = w.find(L';', a);
            std::wstring one = Trim(w.substr(a, (b == std::wstring::npos ? w.size() : b) - a));
            if (!one.empty()) libs.push_back(one);
            if (b == std::wstring::npos) break;
            a = b + 1;
        }
    }
    return libs;
}

static void WriteDefaultConfig() {
    wchar_t up[MAX_PATH];
    std::wstring def = L"libraries=" + (GetEnvironmentVariableW(L"USERPROFILE", up, MAX_PATH)
                       ? (std::wstring(up) + L"\\Videos") : L"C:\\Videos") + L"\n";
    HANDLE f = CreateFileW(ConfigPath().c_str(), GENERIC_WRITE, 0, nullptr,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f != INVALID_HANDLE_VALUE) {
        DWORD wr = 0;
        WriteFile(f, def.c_str(), (DWORD)def.size(), &wr, nullptr);
        CloseHandle(f);
    }
}

// ---------------------------------------------------------------- app
class App {
public:
    int Run(HINSTANCE hinst) {
        if (FAILED(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE)))
            return 1;
        if (FAILED(D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED, m_d2d.GetAddressOf())) ||
            FAILED(DWriteCreateFactory(DWRITE_FACTORY_TYPE_SHARED, __uuidof(IDWriteFactory),
                                       (IUnknown**)m_write.GetAddressOf())) ||
            FAILED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER,
                                    __uuidof(IWICImagingFactory), (void**)m_wic.GetAddressOf()))) {
            CoUninitialize();
            MessageBoxW(nullptr, L"Failed to initialize Direct2D / DirectWrite.",
                        L"Oke Launcher", MB_ICONERROR);
            return 1;
        }

        BuildLibrary();
        if (!CreateWindow_(hinst)) return 1;
        MessageLoop();
        CoUninitialize();
        return 0;
    }

private:
    HWND m_hwnd = nullptr;
    ComPtr<ID2D1Factory>       m_d2d;
    ComPtr<IDWriteFactory>     m_write;
    ComPtr<IWICImagingFactory> m_wic;

    ComPtr<ID2D1HwndRenderTarget> m_rt;
    ComPtr<ID2D1SolidColorBrush> m_brBg, m_brText, m_brDim, m_brMid, m_brAccent, m_brHair;
    ComPtr<ID2D1LinearGradientBrush> m_brBgGrad;

    ComPtr<IDWriteTextFormat> m_fmtTitle;     // app name
    ComPtr<IDWriteTextFormat> m_fmtSmall;     // caps labels
    ComPtr<IDWriteTextFormat> m_fmtItem;      // tile title
    ComPtr<IDWriteTextFormat> m_fmtSub;       // tile subtitle
    ComPtr<IDWriteTextFormat> m_fmtSearch;    // search text
    ComPtr<IDWriteTextFormat> m_fmtBig;       // big fallback initial

    std::vector<MediaItem>   m_items;
    std::vector<size_t>      m_view;          // filtered indices
    std::wstring             m_query;

    float m_scroll = 0.f, m_scrollMax = 0.f;
    int   m_hoverItem = -1;
    int   m_selItem   = -1;
    UINT  m_dpi = 96;
    bool  m_caretOn = true;

    D2D1_RECT_F m_rClose = {}, m_rMax = {}, m_rMin = {};
    int m_hoverBtn = 0;                       // 1 close 2 max 3 min

    struct Layout {
        float s, tileW, tileH, gap, padX, headerH, searchH, gridTop, gridBottom, gridW;
    };

    std::map<std::wstring, ID2D1Bitmap*> m_posterCache;
    std::set<std::wstring> m_posterFailed;

    void Invalidate() { if (m_hwnd) InvalidateRect(m_hwnd, nullptr, FALSE); }

    // ------------------------------------------------------------ window
    bool CreateWindow_(HINSTANCE hinst) {
        WNDCLASSEXW wc = { sizeof(wc) };
        wc.style         = CS_HREDRAW | CS_VREDRAW;
        wc.lpfnWndProc   = &App::WndProcStatic;
        wc.hInstance     = hinst;
        wc.hCursor       = LoadCursorW(nullptr, IDC_ARROW);
        wc.hIcon         = LoadIconW(hinst, MAKEINTRESOURCEW(1));
        wc.hIconSm       = wc.hIcon;
        wc.lpszClassName = L"OkeLauncherWnd";
        RegisterClassExW(&wc);

        int w = MulDiv(1180, (int)m_dpi, 96);
        int h = MulDiv(740, (int)m_dpi, 96);
        RECT wr = { 0, 0, w, h };
        AdjustWindowRect(&wr, WS_OVERLAPPEDWINDOW, FALSE);

        m_hwnd = CreateWindowExW(0, wc.lpszClassName, L"Oke Launcher",
                                 WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                 CW_USEDEFAULT, CW_USEDEFAULT,
                                 wr.right - wr.left, wr.bottom - wr.top,
                                 nullptr, nullptr, hinst, this);
        if (!m_hwnd) return false;

        BOOL pref = 2;   // DWMWCP_ROUND
        DwmSetWindowAttribute(m_hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, &pref, sizeof(pref));
        BOOL dark = TRUE;
        DwmSetWindowAttribute(m_hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, &dark, sizeof(dark));

        SetTimer(m_hwnd, 1, 530, nullptr);
        return true;
    }

    void MessageLoop() {
        MSG msg;
        while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }

    // ------------------------------------------------------------ library
    void BuildLibrary() {
        std::vector<std::wstring> libs = ReadLibraries();
        if (libs.empty()) {
            WriteDefaultConfig();
            libs = ReadLibraries();
        }
        m_items.clear();
        for (const std::wstring& lib : libs) {
            DWORD a = GetFileAttributesW(lib.c_str());
            if (a == INVALID_FILE_ATTRIBUTES || !(a & FILE_ATTRIBUTE_DIRECTORY)) continue;
            std::wstring label = FileName(lib);
            if (label.empty()) label = lib;
            ScanDirectory(lib, 0, 5, label, m_items);
        }
        std::sort(m_items.begin(), m_items.end(), [](const MediaItem& a, const MediaItem& b) {
            return _wcsicmp(a.title.c_str(), b.title.c_str()) < 0;
        });
        ApplyFilter();
    }

    void ApplyFilter() {
        m_view.clear();
        std::wstring q = ToLower(m_query);
        for (size_t i = 0; i < m_items.size(); ++i) {
            if (q.empty() || ToLower(m_items[i].title).find(q) != std::wstring::npos ||
                ToLower(m_items[i].sub).find(q) != std::wstring::npos)
                m_view.push_back(i);
        }
        m_scroll = 0; m_scrollMax = 0;
        m_selItem = -1; m_hoverItem = -1;
        Invalidate();
    }

    void DiscardBitmaps() {
        for (auto& kv : m_posterCache) if (kv.second) kv.second->Release();
        m_posterCache.clear();
        m_posterFailed.clear();
    }

    // ------------------------------------------------------------ resources
    HRESULT CreateTextFormats() {
        m_fmtTitle.Reset(); m_fmtSmall.Reset(); m_fmtItem.Reset();
        m_fmtSub.Reset();   m_fmtSearch.Reset(); m_fmtBig.Reset();
        float s = (float)m_dpi / 96.f;

        auto mk = [&](float px, DWRITE_FONT_WEIGHT w, IDWriteTextFormat** out) {
            return m_write->CreateTextFormat(
                L"Segoe UI", nullptr, w, DWRITE_FONT_STYLE_NORMAL,
                DWRITE_FONT_STRETCH_NORMAL, px, L"en-us", out);
        };
        auto mkcaps = [&](float px, DWRITE_FONT_WEIGHT w, IDWriteTextFormat** out) {
            HRESULT hr = mk(px, w, out);
            if (FAILED(hr)) return hr;
            ComPtr<IDWriteTextFormat1> f1;
            if (SUCCEEDED((*out)->QueryInterface(f1.GetAddressOf())))
                f1->SetLetterSpacing(2.6f * s, DWRITE_TEXT_RANGE{ 0, 260 });
            return hr;
        };
        auto noline = [&](IDWriteTextFormat* f) {
            ComPtr<IDWriteTextFormat1> f1;
            if (SUCCEEDED(f->QueryInterface(f1.GetAddressOf())))
                f1->SetLetterSpacing(0.f, DWRITE_TEXT_RANGE{ 0, 260 });
        };

        HRESULT hr;
        if (FAILED(hr = mk(19.f * s, DWRITE_FONT_WEIGHT_SEMI_BOLD, &m_fmtTitle))) return hr;
        noline(m_fmtTitle.Get());
        if (FAILED(hr = mkcaps(9.5f * s, DWRITE_FONT_WEIGHT_SEMI_BOLD, &m_fmtSmall))) return hr;
        if (FAILED(hr = mk(13.5f * s, DWRITE_FONT_WEIGHT_SEMI_BOLD, &m_fmtItem))) return hr;
        noline(m_fmtItem.Get());
        if (FAILED(hr = mk(10.5f * s, DWRITE_FONT_WEIGHT_NORMAL, &m_fmtSub))) return hr;
        noline(m_fmtSub.Get());
        if (FAILED(hr = mk(16.f * s, DWRITE_FONT_WEIGHT_LIGHT, &m_fmtSearch))) return hr;
        noline(m_fmtSearch.Get());
        if (FAILED(hr = mk(56.f * s, DWRITE_FONT_WEIGHT_LIGHT, &m_fmtBig))) return hr;
        noline(m_fmtBig.Get());
        return S_OK;
    }

    HRESULT CreateResources(int widthPx, int heightPx) {
        if (m_rt) return S_OK;
        UINT dpi = GetDpiForWindow(m_hwnd);
        if (dpi != m_dpi || !m_fmtTitle) {
            m_dpi = dpi;
            HRESULT fhr = CreateTextFormats();
            if (FAILED(fhr)) return fhr;
        }

        D2D1_RENDER_TARGET_PROPERTIES props = D2D1::RenderTargetProperties();
        props.dpiX = (FLOAT)m_dpi;
        props.dpiY = (FLOAT)m_dpi;
        HRESULT hr = m_d2d->CreateHwndRenderTarget(
            props,
            D2D1::HwndRenderTargetProperties(m_hwnd, D2D1::SizeU((UINT32)widthPx, (UINT32)heightPx)),
            &m_rt);
        if (FAILED(hr)) return hr;

        auto solid = [&](const D2D1_COLOR_F& c, ID2D1SolidColorBrush** b) {
            return m_rt->CreateSolidColorBrush(c, b);
        };
        if (FAILED(solid(theme::Background, &m_brBg)))     return E_FAIL;
        if (FAILED(solid(theme::Text,     &m_brText)))     return E_FAIL;
        if (FAILED(solid(theme::TextDim,  &m_brDim)))      return E_FAIL;
        if (FAILED(solid(theme::TextMid,  &m_brMid)))      return E_FAIL;
        if (FAILED(solid(theme::Accent,   &m_brAccent)))   return E_FAIL;
        if (FAILED(solid(theme::Hairline, &m_brHair)))     return E_FAIL;

        D2D1_GRADIENT_STOP gs[2] = {
            { 0.0f, { 0.050f, 0.070f, 0.105f, 1.f } },
            { 1.0f, { 0.024f, 0.032f, 0.050f, 1.f } },
        };
        ComPtr<ID2D1GradientStopCollection> stops;
        m_rt->CreateGradientStopCollection(gs, 2, D2D1_GAMMA_2_2, D2D1_EXTEND_MODE_CLAMP, &stops);
        m_rt->CreateLinearGradientBrush(
            D2D1::LinearGradientBrushProperties(D2D1::Point2F(0, 0), D2D1::Point2F(0, 3000)),
            stops.Get(), &m_brBgGrad);

        return S_OK;
    }

    void DiscardResources() {
        m_rt.Reset();
        m_brBg.Reset(); m_brText.Reset(); m_brDim.Reset(); m_brMid.Reset();
        m_brAccent.Reset(); m_brHair.Reset(); m_brBgGrad.Reset();
        m_fmtTitle.Reset(); m_fmtSmall.Reset(); m_fmtItem.Reset();
        m_fmtSub.Reset(); m_fmtSearch.Reset(); m_fmtBig.Reset();
        DiscardBitmaps();
    }

    // ------------------------------------------------------------ measuring
    float MeasureWidth(const std::wstring& s, IDWriteTextFormat* fmt) {
        if (s.empty()) return 0.f;
        ComPtr<IDWriteTextLayout> lay;
        if (FAILED(m_write->CreateTextLayout(s.c_str(), (UINT32)s.size(), fmt,
                                             4096.f, 200.f, &lay))) return 0.f;
        DWRITE_TEXT_METRICS tm;
        if (FAILED(lay->GetMetrics(&tm))) return 0.f;
        return tm.widthIncludingTrailingWhitespace;
    }

    std::wstring FitText(const std::wstring& text, IDWriteTextFormat* fmt, float maxW) {
        if (text.empty() || MeasureWidth(text, fmt) <= maxW) return text;
        float ellW = MeasureWidth(L"\x2026", fmt);
        if (ellW > maxW) return L"";
        std::wstring t = text;
        while (t.size() > 1) {
            t.pop_back();
            if (MeasureWidth(t + L"\x2026", fmt) <= maxW) return t + L"\x2026";
        }
        return L"";
    }

    // ------------------------------------------------------------ layout
    Layout GetLayout() {
        RECT rc; GetClientRect(m_hwnd, &rc);
        Layout L;
        L.s = (float)m_dpi / 96.f;
        float s = L.s;
        L.tileW   = 168.f * s;
        L.tileH   = 286.f * s;
        L.gap     = 22.f  * s;
        L.padX    = 34.f  * s;
        L.headerH = 66.f  * s;
        L.searchH = 58.f  * s;
        L.gridTop    = L.headerH + L.searchH;
        L.gridBottom = (float)rc.bottom - 32.f * s;
        L.gridW      = (float)rc.right - L.padX * 2.f;
        return L;
    }

    int ColumnsFor(const Layout& L) const {
        float u = L.tileW + L.gap;
        return std::max(1, (int)((L.gridW + L.gap) / u));
    }

    D2D1_RECT_F TileRect(const Layout& L, int idx) const {
        int cols = ColumnsFor(L);
        float unitW = L.tileW + L.gap;
        float usedW = cols * L.tileW + (cols - 1) * L.gap;
        float originX = L.padX + (L.gridW - usedW) * 0.5f;
        int row = idx / cols, col = idx % cols;
        float x = originX + col * unitW;
        float y = L.gridTop - m_scroll + row * (L.tileH + L.gap);
        return D2D1::RectF(x, y, x + L.tileW, y + L.tileH);
    }

    int ItemAt(const Layout& L, float x, float y) const {
        if (x < L.padX || y < L.gridTop) return -1;
        int cols = ColumnsFor(L);
        float unitW = L.tileW + L.gap;
        float usedW = cols * L.tileW + (cols - 1) * L.gap;
        float originX = L.padX + (L.gridW - usedW) * 0.5f;
        float rel = x - originX;
        if (rel < 0) return -1;
        int col = (int)(rel / unitW);
        float within = rel - col * unitW;
        if (col >= cols || within > L.tileW) return -1;
        float yr = y - L.gridTop + m_scroll;
        float unitH = L.tileH + L.gap;
        int row = (int)(yr / unitH);
        if (row < 0 || (yr - row * unitH) > L.tileH) return -1;
        int idx = row * cols + col;
        return (idx >= 0 && idx < (int)m_view.size()) ? idx : -1;
    }

    // ------------------------------------------------------------ posters
    ID2D1Bitmap* PosterBitmap(const std::wstring& posterPath) {
        if (posterPath.empty()) return nullptr;
        if (m_posterFailed.count(posterPath)) return nullptr;
        auto it = m_posterCache.find(posterPath);
        if (it != m_posterCache.end()) return it->second;

        ComPtr<IWICBitmapDecoder> dec;
        if (FAILED(m_wic->CreateDecoderFromFilename(posterPath.c_str(), nullptr,
                 GENERIC_READ, WICDecodeMetadataCacheOnDemand, &dec))) {
            m_posterFailed.insert(posterPath); return nullptr;
        }
        ComPtr<IWICBitmapFrameDecode> frame;
        if (FAILED(dec->GetFrame(0, &frame))) {
            m_posterFailed.insert(posterPath); return nullptr;
        }
        ComPtr<IWICFormatConverter> conv;
        if (FAILED(m_wic->CreateFormatConverter(&conv)) ||
            FAILED(conv->Initialize(frame.Get(), GUID_WICPixelFormat32bppPBGRA,
                 WICBitmapDitherTypeNone, nullptr, 0.0, WICBitmapPaletteTypeCustom))) {
            m_posterFailed.insert(posterPath); return nullptr;
        }
        ID2D1Bitmap* bmp = nullptr;
        if (FAILED(m_rt->CreateBitmapFromWicBitmap(conv.Get(), nullptr, &bmp))) {
            m_posterFailed.insert(posterPath); return nullptr;
        }
        m_posterCache[posterPath] = bmp;
        if (m_posterCache.size() > 400) {          // simple memory guard
            auto victim = m_posterCache.begin();
            if (victim->second) victim->second->Release();
            m_posterCache.erase(victim);
        }
        return bmp;
    }

    // ------------------------------------------------------------ painting
    void OnPaint() {
        RECT rc; GetClientRect(m_hwnd, &rc);
        if (rc.right <= 0 || rc.bottom <= 0) return;
        if (FAILED(CreateResources(rc.right, rc.bottom)) || !m_rt) return;

        m_rt->BeginDraw();
        Layout L = GetLayout();

        m_rt->Clear(theme::Background);
        if (m_brBgGrad)
            m_rt->FillRectangle(D2D1::RectF(0, 0, (float)rc.right, (float)rc.bottom),
                                m_brBgGrad.Get());

        PaintHeader(L);
        PaintSearch(L);
        PaintGrid(L, rc);
        PaintFooter(L);

        HRESULT hr = m_rt->EndDraw();
        if (hr == (HRESULT)D2DERR_RECREATE_TARGET) DiscardResources();
    }

    void HairLine(float x0, float y, float x1) {
        m_rt->DrawLine(D2D1::Point2F(x0, y), D2D1::Point2F(x1, y), m_brHair.Get(), 1.f);
    }

    void PaintHeader(const Layout& L) {
        RECT rc; GetClientRect(m_hwnd, &rc);
        float W = (float)rc.right;
        float s = L.s;
        float pad = L.padX;

        D2D1_RECT_F rName = D2D1::RectF(pad, 14.f * s, pad + 400.f * s, 40.f * s);
        m_rt->DrawTextW(L"OKE", 3, m_fmtTitle.Get(), rName, m_brText.Get());
        D2D1_RECT_F rTag = D2D1::RectF(pad + 58.f * s, 16.f * s, pad + 500.f * s, 40.f * s);
        m_rt->DrawTextW(L"MEDIA LAUNCHER", 14, m_fmtSmall.Get(), rTag, m_brDim.Get());

        SYSTEMTIME st; GetLocalTime(&st);
        wchar_t clock[16];
        swprintf_s(clock, L"%02d:%02d", st.wHour, st.wMinute);
        float clockW = MeasureWidth(clock, m_fmtSmall.Get()) + 10.f * s;
        D2D1_RECT_F rClock = D2D1::RectF(W - pad - clockW, 16.f * s, W - pad, 44.f * s);
        m_rt->DrawTextW(clock, (UINT32)wcslen(clock), m_fmtSmall.Get(), rClock, m_brMid.Get());

        HairLine(pad, L.headerH - 10.f * s, W - pad);

        float b = 42.f * s, g = 4.f * s;
        float y0 = 6.f * s;
        m_rClose = { W - pad - g - b, y0, W - pad - g, y0 + b };
        m_rMax   = { W - pad - g * 2 - b * 2, y0, W - pad - g - b, y0 + b };
        m_rMin   = { W - pad - g * 3 - b * 3, y0, W - pad - g * 2 - b * 2, y0 + b };
        if (m_hoverBtn) {
            D2D1_RECT_F rr = (m_hoverBtn == 1) ? m_rClose : (m_hoverBtn == 2) ? m_rMax : m_rMin;
            D2D1_ROUNDED_RECT rrq = D2D1::RoundedRect(rr, 5.f * s, 5.f * s);
            m_rt->FillRoundedRectangle(rrq, (m_hoverBtn == 1) ? m_brAccent.Get() : m_brBg.Get());
        }
        float half = b * 0.30f;
        auto center = [&](const D2D1_RECT_F& r, float& cx, float& cy) {
            cx = (r.left + r.right) / 2; cy = (r.top + r.bottom) / 2;
        };
        float cx, cy;
        center(m_rClose, cx, cy);
        m_rt->DrawLine(D2D1::Point2F(cx - half, cy - half), D2D1::Point2F(cx + half, cy + half),
                       m_brMid.Get(), 1.2f * s);
        m_rt->DrawLine(D2D1::Point2F(cx - half, cy + half), D2D1::Point2F(cx + half, cy - half),
                       m_brMid.Get(), 1.2f * s);
        center(m_rMax, cx, cy);
        m_rt->DrawRectangle(D2D1::RectF(cx - half, cy - half, cx + half, cy + half),
                            m_brMid.Get(), 1.2f * s);
        center(m_rMin, cx, cy);
        m_rt->DrawLine(D2D1::Point2F(cx - half, cy), D2D1::Point2F(cx + half, cy),
                       m_brMid.Get(), 1.2f * s);
    }

    void PaintSearch(const Layout& L) {
        RECT rc; GetClientRect(m_hwnd, &rc);
        float W = (float)rc.right;
        float s = L.s;
        float y = L.headerH + 6.f * s;
        float x0 = L.padX, x1 = W - L.padX;

        float caretX;
        if (!m_query.empty()) {
            D2D1_RECT_F rq = D2D1::RectF(x0, y, x1, y + 30.f * s);
            m_rt->DrawTextW(m_query.c_str(), (UINT32)m_query.size(), m_fmtSearch.Get(),
                            rq, m_brText.Get());
            caretX = x0 + MeasureWidth(m_query, m_fmtSearch.Get());
        } else {
            D2D1_RECT_F rq = D2D1::RectF(x0, y, x1, y + 30.f * s);
            m_rt->DrawTextW(L"SEARCH LIBRARY", 14, m_fmtSmall.Get(), rq, m_brDim.Get());
            caretX = x0 + MeasureWidth(L"SEARCH LIBRARY", m_fmtSmall.Get());
        }
        if (m_caretOn && caretX + 8.f * s < x1) {
            D2D1_RECT_F rcaret = D2D1::RectF(caretX + 7.f * s, y + 3.f * s,
                                             caretX + 8.4f * s, y + 24.f * s);
            m_rt->FillRectangle(rcaret, m_brAccent.Get());
        }

        wchar_t cnt[64];
        swprintf_s(cnt, L"%d TITLES", (int)m_view.size());
        float cntW = MeasureWidth(cnt, m_fmtSmall.Get()) + 10.f * s;
        D2D1_RECT_F rcnt = D2D1::RectF(x1 - cntW, y + 2.f * s, x1, y + 26.f * s);
        m_rt->DrawTextW(cnt, (UINT32)wcslen(cnt), m_fmtSmall.Get(), rcnt, m_brDim.Get());

        HairLine(x0, L.gridTop - 14.f * s, x1);
    }

    // ------------------------------------------------------------ grid
    void PosterRect(const Layout& L, const D2D1_RECT_F& tile, D2D1_RECT_F& out) const {
        out = D2D1::RectF(tile.left, tile.top, tile.right, tile.top + 240.f * L.s);
    }

    void PaintGrid(const Layout& L, const RECT& rc) {
        float s = L.s;
        int cols = ColumnsFor(L);
        float rows = (float)((m_view.size() + cols - 1) / cols);
        m_scrollMax = std::max(0.f, rows * (L.tileH + L.gap) - (L.gridBottom - L.gridTop));
        m_scroll = std::clamp(m_scroll, 0.f, m_scrollMax);

        D2D1_RECT_F clip = D2D1::RectF(0, L.gridTop, (float)rc.right, L.gridBottom);
        m_rt->PushAxisAlignedClip(clip, D2D1_ANTIALIAS_MODE_PER_PRIMITIVE);

        if (m_view.empty()) {
            PaintEmpty(L, rc);
            m_rt->PopAxisAlignedClip();
            return;
        }

        int firstRow = std::max(0, (int)(m_scroll / (L.tileH + L.gap)));
        int lastRow  = std::min(((int)m_view.size() - 1) / cols,
                                firstRow + (int)((L.gridBottom - L.gridTop) / (L.tileH + L.gap)) + 1);

        ComPtr<ID2D1RoundedRectangleGeometry> geo;
        if (FAILED(m_d2d->CreateRoundedRectangleGeometry(D2D1::RoundedRect(
                D2D1::RectF(0, 0, L.tileW, 240.f * s), 7.f * s, 7.f * s), &geo))) {
            m_rt->PopAxisAlignedClip();
            return;
        }

        for (int i = firstRow * cols; i < std::min((int)m_view.size(), (lastRow + 1) * cols); ++i) {
            D2D1_RECT_F tile = TileRect(L, i);
            if (tile.bottom < L.gridTop || tile.top > L.gridBottom) continue;
            PaintTile(L, i, tile, geo.Get());
        }
        m_rt->PopAxisAlignedClip();

        if (m_scrollMax > 0) {          // slim scroll indicator
            float x = (float)rc.right - 8.f * s;
            float track = L.gridBottom - L.gridTop;
            float th = std::max(36.f * s, track * track / (track + m_scrollMax));
            float ty = L.gridTop + (m_scroll / m_scrollMax) * (track - th);
            m_rt->FillRoundedRectangle(
                D2D1::RoundedRect(D2D1::RectF(x, ty, x + 2.5f * s, ty + th),
                                  1.2f * s, 1.2f * s),
                m_brHair.Get());
        }
    }

    void PaintTile(const Layout& L, int i, const D2D1_RECT_F& tile, ID2D1Geometry* geo) {
        const MediaItem& it = m_items[m_view[i]];
        bool hover = (i == m_hoverItem);
        bool sel   = (i == m_selItem);

        D2D1_RECT_F pr;
        PosterRect(L, tile, pr);

        ID2D1Bitmap* bmp = PosterBitmap(it.poster);
        if (bmp) {
            D2D1_LAYER_PARAMETERS lp = D2D1::LayerParameters();
            lp.contentBounds = D2D1::InflateRect(pr, 2.f, 2.f);
            lp.geometricMask = geo;
            lp.maskTransform = D2D1::Matrix3x2F::Translation(pr.left, pr.top);
            lp.opacity = 1.f;
            lp.opacityBrush = nullptr;
            lp.layerOptions = D2D1_LAYER_OPTIONS_NONE;
            m_rt->PushLayer(lp, nullptr);
            DrawCover(bmp, pr);
            m_rt->PopLayer();
        } else {
            D2D1_ROUNDED_RECT rr = D2D1::RoundedRect(pr, 7.f * L.s, 7.f * L.s);
            m_rt->FillRoundedRectangle(rr, m_brBg.Get());
            m_rt->DrawRoundedRectangle(rr, m_brHair.Get(), 1.f);
            wchar_t ini[2] = { (wchar_t)std::towupper(it.title.empty() ? L'?' : it.title[0]), 0 };
            D2D1_RECT_F rini = D2D1::RectF(pr.left, pr.top + (pr.bottom - pr.top) * 0.30f,
                                           pr.right, pr.bottom);
            m_rt->DrawTextW(ini, 1, m_fmtBig.Get(), rini, m_brAccent.Get());
        }

        D2D1_ROUNDED_RECT edge = D2D1::RoundedRect(D2D1::InflateRect(pr, 2.f, 2.f),
                                                   8.f * L.s, 8.f * L.s);
        if (sel)       m_rt->DrawRoundedRectangle(edge, m_brAccent.Get(), 1.8f * L.s);
        else if (hover) m_rt->DrawRoundedRectangle(edge, m_brAccent.Get(), 1.4f * L.s);

        float tw = L.tileW;
        std::wstring title = FitText(it.title, m_fmtItem.Get(), tw);
        D2D1_RECT_F rt = D2D1::RectF(tile.left, tile.top + 246.f * L.s,
                                     tile.right, tile.top + 270.f * L.s);
        m_rt->DrawTextW(title.c_str(), (UINT32)title.size(), m_fmtItem.Get(), rt, m_brText.Get());
        if (!it.sub.empty()) {
            std::wstring sub = FitText(it.sub, m_fmtSub.Get(), tw);
            D2D1_RECT_F rs = D2D1::RectF(tile.left, tile.top + 268.f * L.s,
                                         tile.right, tile.top + 286.f * L.s);
            m_rt->DrawTextW(sub.c_str(), (UINT32)sub.size(), m_fmtSub.Get(), rs, m_brDim.Get());
        }
    }

    void DrawCover(ID2D1Bitmap* bmp, const D2D1_RECT_F& dst) {
        D2D1_SIZE_F sz = bmp->GetSize();
        if (sz.width <= 0 || sz.height <= 0) return;
        float dstW = dst.right - dst.left, dstH = dst.bottom - dst.top;
        float scale = std::max(dstW / sz.width, dstH / sz.height);
        float w = sz.width * scale, h = sz.height * scale;
        float cx = (dst.left + dst.right) * 0.5f, cy = (dst.top + dst.bottom) * 0.5f;
        m_rt->DrawBitmap(bmp, D2D1::RectF(cx - w * 0.5f, cy - h * 0.5f,
                                          cx + w * 0.5f, cy + h * 0.5f));
    }

    void PaintEmpty(const Layout& L, const RECT& rc) {
        float cx = (float)rc.right * .5f, cy = (L.gridTop + L.gridBottom) * .5f;
        D2D1_RECT_F r1 = D2D1::RectF(cx - 260.f * L.s, cy - 46.f * L.s, cx + 260.f * L.s, cy);
        m_rt->DrawTextW(L"NO TITLES FOUND", 15, m_fmtSmall.Get(), r1, m_brDim.Get());
        D2D1_RECT_F r2 = D2D1::RectF(cx - 320.f * L.s, cy + 4.f * L.s, cx + 320.f * L.s,
                                     cy + 44.f * L.s);
        m_rt->DrawTextW(
            L"Add folders to oke.cfg  ·  press F5 to rescan",
            (UINT32)wcslen(L"Add folders to oke.cfg  ·  press F5 to rescan"),
            m_fmtSub.Get(), r2, m_brDim.Get());
    }

    void PaintFooter(const Layout& L) {
        RECT rc; GetClientRect(m_hwnd, &rc);
        D2D1_RECT_F rh = D2D1::RectF(L.padX, (float)rc.bottom - 26.f * L.s,
                                     (float)rc.right - L.padX, (float)rc.bottom);
        m_rt->DrawTextW(
            L"TYPE TO SEARCH   ·   ENTER PLAYS SELECTION   ·   ESC CLEARS   ·   F5 RESCAN",
            (UINT32)wcslen(L"TYPE TO SEARCH   ·   ENTER PLAYS SELECTION   ·   ESC CLEARS   ·   F5 RESCAN"),
            m_fmtSmall.Get(), rh, m_brDim.Get());
    }

    // ------------------------------------------------------------ interaction
    void EnsureVisible(int idx, const Layout& L) {
        if (idx < 0) return;
        D2D1_RECT_F t = TileRect(L, idx);
        if (t.top < L.gridTop) m_scroll -= (L.gridTop - t.top);
        else if (t.bottom > L.gridBottom) m_scroll += (t.bottom - L.gridBottom);
        m_scroll = std::clamp(m_scroll, 0.f, m_scrollMax);
    }

    void SelectMove(int delta) {
        if (m_view.empty()) return;
        if (m_selItem < 0) m_selItem = (delta > 0) ? 0 : (int)m_view.size() - 1;
        else m_selItem = std::clamp(m_selItem + delta, 0, (int)m_view.size() - 1);
        EnsureVisible(m_selItem, GetLayout());
        Invalidate();
    }

    void Launch(int idx) {
        if (idx < 0 || idx >= (int)m_view.size()) return;
        const std::wstring& path = m_items[m_view[idx]].path;
        SHELLEXECUTEINFOW sei = { sizeof(sei) };
        sei.lpVerb = L"open";
        sei.lpFile = path.c_str();
        sei.nShow  = SW_SHOWNORMAL;
        sei.fMask  = SEE_MASK_FLAG_NO_UI;
        if (!ShellExecuteExW(&sei))
            MessageBoxW(m_hwnd, (L"Could not open:\n" + path).c_str(),
                        L"Oke Launcher", MB_ICONWARNING);
    }

    int BtnAt(float x, float y) const {
        auto in = [&](const D2D1_RECT_F& r) {
            return r.left <= x && x <= r.right && r.top <= y && y <= r.bottom;
        };
        if (in(m_rClose)) return 1;
        if (in(m_rMax))   return 2;
        if (in(m_rMin))   return 3;
        return 0;
    }

    void UpdateHover(LPARAM lp) {
        POINT pt{ GET_X_LPARAM(lp), GET_Y_LPARAM(lp) };
        Layout L = GetLayout();
        int newItem = ItemAt(L, (float)pt.x, (float)pt.y);
        int newBtn  = BtnAt((float)pt.x, (float)pt.y);
        if (newItem != m_hoverItem || newBtn != m_hoverBtn) Invalidate();
        m_hoverItem = newItem;
        m_hoverBtn = newBtn;
        TRACKMOUSEEVENT tme = { sizeof(tme), TME_LEAVE, m_hwnd, 0 };
        TrackMouseEvent(&tme);
    }

    // ------------------------------------------------------------ wndproc
    static LRESULT CALLBACK WndProcStatic(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
        App* self = nullptr;
        if (msg == WM_NCCREATE) {
            CREATESTRUCTW* cs = (CREATESTRUCTW*)lp;
            self = (App*)cs->lpCreateParams;
            SetWindowLongPtrW(hwnd, GWLP_USERDATA, (LONG_PTR)self);
            self->m_hwnd = hwnd;
        } else {
            self = (App*)GetWindowLongPtrW(hwnd, GWLP_USERDATA);
        }
        return self ? self->WndProc(hwnd, msg, wp, lp)
                    : DefWindowProcW(hwnd, msg, wp, lp);
    }

    LRESULT WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
        switch (msg) {
        case WM_PAINT:
            OnPaint();
            ValidateRect(hwnd, nullptr);
            return 0;

        case WM_SIZE: {
            int w = LOWORD(lp), h = HIWORD(lp);
            if (m_rt && w > 0 && h > 0) {
                m_rt->Resize(D2D1::SizeU(w, h));
                Invalidate();
            }
            return 0;
        }

        case WM_DPICHANGED: {
            m_dpi = HIWORD(wp);
            DiscardResources();
            RECT* r = (RECT*)lp;
            SetWindowPos(hwnd, nullptr, r->left, r->top,
                         r->right - r->left, r->bottom - r->top,
                         SWP_NOZORDER | SWP_NOACTIVATE);
            return 0;
        }

        case WM_NCCALCSIZE:
            if (wp) {
                if (IsZoomed(hwnd)) {
                    int fw = GetSystemMetrics(SM_CXFRAME) + GetSystemMetrics(SM_CXPADDEDBORDER);
                    int fh = GetSystemMetrics(SM_CYFRAME) + GetSystemMetrics(SM_CXPADDEDBORDER);
                    ((RECT*)lp)->left += fw; ((RECT*)lp)->top += fh;
                    ((RECT*)lp)->right -= fw; ((RECT*)lp)->bottom -= fh;
                }
                return 0;
            }
            break;

        case WM_NCHITTEST: {
            POINT pt{ GET_X_LPARAM(lp), GET_Y_LPARAM(lp) };
            ScreenToClient(hwnd, &pt);
            RECT rc; GetClientRect(hwnd, &rc);
            if (!IsZoomed(hwnd)) {
                int b = GetSystemMetrics(SM_CXFRAME) + GetSystemMetrics(SM_CXPADDEDBORDER);
                bool l = pt.x < b, r = pt.x >= rc.right - b;
                bool t = pt.y < b, bo = pt.y >= rc.bottom - b;
                if (t && l) return HTTOPLEFT;
                if (t && r) return HTTOPRIGHT;
                if (bo && l) return HTBOTTOMLEFT;
                if (bo && r) return HTBOTTOMRIGHT;
                if (l) return HTLEFT;
                if (r) return HTRIGHT;
                if (t) return HTTOP;
                if (bo) return HTBOTTOM;
            }
            Layout L = GetLayout();
            if (pt.y < (int)L.headerH && !BtnAt((float)pt.x, (float)pt.y)) return HTCAPTION;
            return HTCLIENT;
        }

        case WM_ACTIVATE:
            Invalidate();
            return DefWindowProcW(hwnd, msg, wp, lp);

        case WM_MOUSEMOVE:
            UpdateHover(lp);
            return 0;

        case WM_MOUSELEAVE:
            m_hoverItem = -1; m_hoverBtn = 0;
            Invalidate();
            return 0;

        case WM_LBUTTONDOWN: {
            POINT pt{ GET_X_LPARAM(lp), GET_Y_LPARAM(lp) };
            int btn = BtnAt((float)pt.x, (float)pt.y);
            if (btn == 1) { PostQuitMessage(0); return 0; }
            if (btn == 2) { if (IsZoomed(hwnd)) ShowWindow(hwnd, SW_RESTORE);
                            else ShowWindow(hwnd, SW_MAXIMIZE); return 0; }
            if (btn == 3) { ShowWindow(hwnd, SW_MINIMIZE); return 0; }
            Layout L = GetLayout();
            int idx = ItemAt(L, (float)pt.x, (float)pt.y);
            if (idx >= 0) { m_selItem = idx; Launch(idx); }
            Invalidate();
            return 0;
        }

        case WM_MOUSEWHEEL: {
            UINT lines = 3;
            SystemParametersInfoW(SPI_GETWHEELSCROLLLINES, 0, &lines, 0);
            float delta = (float)GET_WHEEL_DELTA_WPARAM(wp) / WHEEL_DELTA
                        * (float)lines * 60.f * ((float)m_dpi / 96.f);
            m_scroll = std::clamp(m_scroll - delta, 0.f, std::max(0.f, m_scrollMax));
            Invalidate();
            return 0;
        }

        case WM_CHAR:
            if (wp >= 0x20 && wp <= 0x10FFFF) {
                m_query += (wchar_t)wp;
                ApplyFilter();
            }
            return 0;

        case WM_KEYDOWN:
            switch (wp) {
            case VK_BACK:
                if (!m_query.empty()) { m_query.pop_back(); ApplyFilter(); }
                return 0;
            case VK_ESCAPE:
                if (!m_query.empty()) { m_query.clear(); ApplyFilter(); }
                return 0;
            case VK_RETURN: Launch(m_selItem); return 0;
            case VK_LEFT:  SelectMove(-1); return 0;
            case VK_RIGHT: SelectMove(1);  return 0;
            case VK_UP:    SelectMove(-ColumnsFor(GetLayout())); return 0;
            case VK_DOWN:  SelectMove(ColumnsFor(GetLayout()));  return 0;
            case VK_HOME:  m_selItem = m_view.empty() ? -1 : 0;
                           EnsureVisible(m_selItem, GetLayout()); Invalidate(); return 0;
            case VK_END:   m_selItem = (int)m_view.size() - 1;
                           EnsureVisible(m_selItem, GetLayout()); Invalidate(); return 0;
            case VK_F5:    BuildLibrary(); return 0;
            }
            return DefWindowProcW(hwnd, msg, wp, lp);

        case WM_TIMER:
            if (wp == 1) { m_caretOn = !m_caretOn; Invalidate(); }
            return 0;

        case WM_ERASEBKGND:
            return 1;

        case WM_GETMINMAXINFO: {
            MINMAXINFO* mmi = (MINMAXINFO*)lp;
            UINT dpi = m_hwnd ? GetDpiForWindow(hwnd) : 96;
            mmi->ptMinTrackSize.x = MulDiv(760, (int)dpi, 96);
            mmi->ptMinTrackSize.y = MulDiv(480, (int)dpi, 96);
            return 0;
        }

        case WM_DESTROY:
            PostQuitMessage(0);
            return 0;
        }
        return DefWindowProcW(hwnd, msg, wp, lp);
    }
};

int WINAPI wWinMain(HINSTANCE hinst, HINSTANCE, LPWSTR, int) {
    App app;
    return app.Run(hinst);
}
