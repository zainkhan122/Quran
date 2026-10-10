import { AutoTokenizer, MusicgenForConditionalGeneration, RawAudio } from '@huggingface/transformers';
const mem = () => Math.round(process.memoryUsage().rss/1048576);
console.log('rss start', mem(), 'MB');
let t0 = Date.now();
const tokenizer = await AutoTokenizer.from_pretrained('Xenova/musicgen-small', { cache_dir: './.cache' });
const model = await MusicgenForConditionalGeneration.from_pretrained('Xenova/musicgen-small', {
  cache_dir: './.cache',
  dtype: { text_encoder: 'q8', decoder_model_merged: 'q8', encodec_decode: 'fp32' },
});
console.log(`load ${((Date.now()-t0)/1000).toFixed(1)}s rss ${mem()} MB`);
const prompt = 'soft islamic nasheed instrumental, ney flute, harmonium drone, gentle tabla, devotional, no vocals, 70 bpm';
const inputs = tokenizer(prompt);
t0 = Date.now();
const out = await model.generate({ ...inputs, max_new_tokens: 90, do_sample: true, guidance_scale: 3.0 });
const sr = model.config.audio_encoder.sampling_rate;
const dur = out.dims[out.dims.length-1]/sr;
console.log(`gen ${((Date.now()-t0)/1000).toFixed(1)}s for ${dur.toFixed(1)}s audio RTF=${(((Date.now()-t0)/1000)/dur).toFixed(2)}x rss ${mem()} MB`);
const audio = new RawAudio(out.data, sr);
await audio.save('test/musicgen_backing.wav');
console.log('saved');
