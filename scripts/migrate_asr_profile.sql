-- Migration: meeting-asr profile → sensevoice-small
-- Date: 2026-07-24
-- Bug: meeting-asr profile pointed to disabled whisper-small (faster-whisper provider)
-- Fix: rebind to sensevoice-small (sensevoice-onnx provider, enabled)

UPDATE ms_model_profiles
SET model_id = (
    SELECT model_id FROM ms_models
    WHERE name = 'sensevoice-small' AND model_type = 'asr' AND status = 'enabled'
    LIMIT 1
)
WHERE name = 'meeting-asr'
  AND model_id IN (
      SELECT model_id FROM ms_models
      WHERE model_type = 'asr' AND status = 'disabled'
  );
