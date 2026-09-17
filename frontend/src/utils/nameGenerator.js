/**
 * Universal project name generator based on input source (URL or local file).
 * Produces clean, filesystem-safe, descriptive folder names.
 */
export function generateProjectNameFromUrl(source) {
  if (!source || typeof source !== 'string') return '';
  const trimmed = source.trim();

  // 1. Web URLs
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    try {
      const url = new URL(trimmed);
      const host = url.hostname.toLowerCase();
      const pathname = url.pathname;

      // Webtoons / AsuraScans / Manga
      // e.g. /comics/30-years-since-the-prologue-b57aa235/chapter/1
      const manhwaMatch = pathname.match(/comics\/([^/]+)(?:\/chapter\/(\d+))?/i) ||
                          pathname.match(/series\/([^/]+)(?:\/chapter\/(\d+))?/i) ||
                          pathname.match(/manga\/([^/]+)(?:\/chapter\/(\d+))?/i);
      if (manhwaMatch) {
        let slug = manhwaMatch[1].replace(/-[a-f0-9]{6,}$/i, ''); // Strip trailing random hashes if present
        slug = slug.replace(/[^a-zA-Z0-9_-]/g, '_');
        const chapter = manhwaMatch[2] ? `_ch${manhwaMatch[2]}` : '';
        return `${slug}${chapter}`.toLowerCase();
      }

      // YouTube
      if (host.includes('youtube.com') || host.includes('youtu.be')) {
        const vParam = url.searchParams.get('v');
        if (vParam) return `yt_${vParam}`;
        const shortMatch = pathname.match(/\/([a-zA-Z0-9_-]{11})/);
        if (shortMatch) return `yt_${shortMatch[1]}`;
      }

      // Bilibili
      if (host.includes('bilibili.com')) {
        const biliMatch = pathname.match(/(BV[0-9A-Za-z]{10}|av\d+)/i);
        if (biliMatch) return `bilibili_${biliMatch[1]}`;
      }

      // TikTok / Douyin
      if (host.includes('tiktok.com') || host.includes('douyin.com')) {
        const ttMatch = pathname.match(/video\/(\d+)/);
        if (ttMatch) return `tiktok_${ttMatch[1]}`;
      }

      // Generic URL fallback: clean domain + last meaningful path segment
      const cleanHost = host.replace(/^www\./, '').split('.')[0].replace(/[^a-zA-Z0-9]/g, '_');
      const segments = pathname.split('/').filter(Boolean);
      const lastSegment = segments.length > 0 ? segments[segments.length - 1].replace(/[^a-zA-Z0-9_-]/g, '_') : '';
      if (lastSegment && lastSegment !== 'index' && lastSegment.length > 2) {
        return `${cleanHost}_${lastSegment}`.slice(0, 40).toLowerCase();
      }
      return `${cleanHost}_project`.toLowerCase();
    } catch (_) {
      // Fall through to generic string cleaning
    }
  }

  // 2. Local File / Path
  // Handles both Windows (C:\path\file.mp4) and POSIX (/path/file.mp4)
  const baseName = trimmed.split(/[/\\]/).pop() || '';
  const nameWithoutExt = baseName.replace(/\.[^/.]+$/, '');
  const cleanLocal = nameWithoutExt.replace(/[^a-zA-Z0-9_-]/g, '_');
  return cleanLocal ? cleanLocal.slice(0, 50).toLowerCase() : 'recap_project';
}
