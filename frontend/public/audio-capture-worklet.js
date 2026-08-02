class AegisPcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = options?.processorOptions?.targetSampleRate || 16000;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    const ratio = sampleRate / this.targetRate;
    const pcm = new Int16Array(Math.max(1, Math.round(channel.length / ratio)));
    let level = 0;
    for (let index = 0; index < pcm.length; index += 1) {
      const sourceIndex = Math.min(channel.length - 1, index * ratio);
      const lower = Math.floor(sourceIndex);
      const upper = Math.min(channel.length - 1, lower + 1);
      const fraction = sourceIndex - lower;
      const sample = channel[lower] + (channel[upper] - channel[lower]) * fraction;
      const value = Math.max(-1, Math.min(1, sample));
      pcm[index] = value < 0 ? value * 0x8000 : value * 0x7fff;
      level = Math.max(level, Math.abs(value));
    }
    this.port.postMessage({ pcm: pcm.buffer, level }, [pcm.buffer]);
    return true;
  }
}

registerProcessor("aegis-pcm-capture", AegisPcmCaptureProcessor);
