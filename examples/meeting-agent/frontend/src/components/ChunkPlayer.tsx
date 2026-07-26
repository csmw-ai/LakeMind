import { useEffect, useRef, useState } from "react";
import { Card, Space, Button, Slider, Typography } from "antd";

interface Props {
  taskId: string;
  chunks: any[];
}

export default function ChunkPlayer({ taskId, chunks }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [currentChunk, setCurrentChunk] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [totalMs, setTotalMs] = useState(0);

  useEffect(() => {
    const total = chunks.reduce((sum, c) => sum + (c.duration_ms || 0), 0);
    setTotalMs(total);
    if (chunks.length > 0) loadChunk(0);
  }, [chunks]);

  async function loadChunk(idx: number, autoplay = false) {
    if (idx >= chunks.length) { setPlaying(false); return; }
    const seq = chunks[idx].sequence_no;
    const resp = await fetch(`/api/tasks/${taskId}/audio/chunks/${seq}`);
    const blob = await resp.blob();
    if (audioRef.current) {
      audioRef.current.src = URL.createObjectURL(blob);
      audioRef.current.playbackRate = rate;
      setCurrentChunk(idx);
      if (autoplay) {
        audioRef.current.play().catch(() => {});
      }
    }
  }

  function onEnded() {
    loadChunk(currentChunk + 1, true);
  }

  function togglePlay() {
    if (!audioRef.current) return;
    if (playing) { audioRef.current.pause(); setPlaying(false); }
    else { audioRef.current.play(); setPlaying(true); }
  }

  function onRateChange(v: number) {
    setRate(v);
    if (audioRef.current) audioRef.current.playbackRate = v;
  }

  function skip(seconds: number) {
    if (audioRef.current) audioRef.current.currentTime += seconds;
  }

  const accBefore = chunks.slice(0, currentChunk).reduce((s, c) => s + (c.duration_ms || 0), 0);
  const displayMs = accBefore + (currentTime * 1000);

  return (
    <Card title="录音回放" size="small" style={{ marginBottom: 16 }}>
      <audio ref={audioRef} onEnded={onEnded} onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)} />
      <Space>
        <Button onClick={togglePlay}>{playing ? "⏸" : "▶"}</Button>
        <Button size="small" onClick={() => skip(-10)}>-10s</Button>
        <Button size="small" onClick={() => skip(10)}>+10s</Button>
        <Slider min={0.75} max={2} step={0.25} value={rate} onChange={onRateChange} style={{ width: 100 }} />
        <Typography.Text>{Math.floor(displayMs / 1000)}s / {Math.floor(totalMs / 1000)}s</Typography.Text>
        <Typography.Text type="secondary">分片 {currentChunk + 1}/{chunks.length}</Typography.Text>
      </Space>
    </Card>
  );
}
