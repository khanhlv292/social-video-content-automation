from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Scene:
    index: int
    text: str
    duration_seconds: int


@dataclass(frozen=True)
class Asset:
    id: str
    kind: str
    source: str
    license: str
    attribution: str


@dataclass(frozen=True)
class AssetManifest:
    assets: list[Asset]


@dataclass(frozen=True)
class VideoPlan:
    package_id: str
    title: str
    scenes: list[Scene]
    asset_manifest: AssetManifest


class TTSProvider(Protocol):
    def synthesize(self, text: str, destination: Path) -> Path:
        """Create a WAV file and return its path."""


class SilentTTSProvider:
    """Deterministic fallback for local dry-runs; replace with a licensed TTS adapter."""

    def synthesize(self, text: str, destination: Path) -> Path:
        duration = max(1, round(len(text) / 14))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(destination), "w") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16_000)
            audio.writeframes(b"\0\0" * 16_000 * duration)
        return destination


class WebhookTTSProvider:
    def __init__(self, url: str) -> None:
        self.url = url

    def synthesize(self, text: str, destination: Path) -> Path:
        payload = json.dumps({"text": text, "format": "wav", "sample_rate": 16_000}).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                audio = response.read()
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"TTS webhook failed: {exc}") from exc
        if not audio:
            raise RuntimeError("TTS webhook returned an empty audio file")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(audio)
        return destination


def build_video_plan(package: dict) -> VideoPlan:
    script = package["script"]
    parts = [part.strip() for part in script.split(".") if part.strip()]
    scenes = [
        Scene(index=index, text=text + ".", duration_seconds=max(3, min(8, round(len(text) / 13))))
        for index, text in enumerate(parts, start=1)
    ]
    return VideoPlan(
        package_id=package["id"],
        title=package["title"],
        scenes=scenes,
        asset_manifest=AssetManifest(
            assets=[
                Asset(
                    id="generated-background",
                    kind="background",
                    source="generated://gradient",
                    license="generated",
                    attribution="",
                )
            ]
        ),
    )


def write_srt(scenes: list[Scene], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    elapsed = 0
    rows: list[str] = []
    for scene in scenes:
        start = _timestamp(elapsed)
        elapsed += scene.duration_seconds
        end = _timestamp(elapsed)
        rows.append(f"{scene.index}\n{start} --> {end}\n{scene.text}\n")
    destination.write_text("\n".join(rows), encoding="utf-8")
    return destination


def render_video(plan: VideoPlan, audio_path: Path, destination: Path) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to render video; install it or use the render Docker image")
    duration = sum(scene.duration_seconds for scene in plan.scenes)
    subtitles = destination.with_suffix(".srt")
    write_srt(plan.scenes, subtitles)
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x172554:s=1080x1920:r=30:d={duration}",
        "-i",
        str(audio_path),
        "-vf",
        f"subtitles={_escape_filter_path(subtitles)}",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        str(destination),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg render failed: {completed.stderr[-1200:]}")
    return destination


def quality_check(video_path: Path, plan: VideoPlan) -> dict:
    if not video_path.exists() or video_path.stat().st_size == 0:
        raise ValueError("rendered video is missing or empty")
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is required for video QA")
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height,codec_name",
            "-of",
            "json",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {probe.stderr[-1200:]}")
    streams = json.loads(probe.stdout).get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    checks = {
        "has_video": video is not None,
        "has_audio": audio is not None,
        "vertical_1080x1920": video is not None and video.get("width") == 1080 and video.get("height") == 1920,
        "h264_video": video is not None and video.get("codec_name") == "h264",
        "aac_audio": audio is not None and audio.get("codec_name") == "aac",
        "asset_manifest_complete": all(asset.license for asset in plan.asset_manifest.assets),
    }
    return {"passed": all(checks.values()), "checks": checks, "streams": streams}


def write_video_artifacts(package: dict, destination: Path) -> dict:
    plan = build_video_plan(package)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "video-plan.json").write_text(json.dumps(asdict(plan), ensure_ascii=False, indent=2) + "\n")
    text = plan.title + " " + " ".join(scene.text for scene in plan.scenes)
    tts_mode = os.getenv("TTS_MODE", "silent").lower()
    if tts_mode == "webhook":
        tts_url = os.getenv("TTS_WEBHOOK_URL")
        if not tts_url:
            raise RuntimeError("TTS_WEBHOOK_URL is required when TTS_MODE=webhook")
        provider: TTSProvider = WebhookTTSProvider(tts_url)
    elif tts_mode == "silent":
        provider = SilentTTSProvider()
    else:
        raise ValueError("TTS_MODE must be silent or webhook")
    audio = provider.synthesize(text, destination / "voice.wav")
    video = render_video(plan, audio, destination / "video.mp4")
    qa = quality_check(video, plan)
    (destination / "qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n")
    if not qa["passed"]:
        raise ValueError("video QA failed")
    return {"video": str(video), "qa": str(destination / "qa.json")}


def _timestamp(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},000"


def _escape_filter_path(path: Path) -> str:
    return os.fspath(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
