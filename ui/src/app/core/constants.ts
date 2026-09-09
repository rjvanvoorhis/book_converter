/**
 * TTS providers and book sources are registered in the backend's
 * composition_root.py, which has no listing endpoint. These mirror that
 * registration and need to stay in sync with it manually.
 */
export interface SelectOption {
  value: string;
  label: string;
}

export interface BookSourceOption extends SelectOption {
  identifierPlaceholder: string;
}

// Matches the backend's default in routes.py / commands.py.
export const DEFAULT_AUDIOBOOK_FOLDER = 'data/audiobooks';

// Matches the backend's default in routes.py.
export const DEFAULT_PRONUNCIATIONS_FOLDER = 'pronunciation-dicts';

// Matches the backend's default in routes.py.
export const DEFAULT_VOICE_SAMPLES_FOLDER = 'data/voice_samples';

/**
 * A compact IPA palette covering the symbols most English pronunciation
 * respellings need, grouped for the picker UI. Most keyboards can't type
 * these directly, so building a value is done by clicking symbols rather
 * than typing them.
 */
export const IPA_SYMBOL_GROUPS: { label: string; symbols: string[] }[] = [
  { label: 'Stress & length', symbols: ['ˈ', 'ˌ', 'ː'] },
  {
    label: 'Vowels',
    symbols: ['i', 'ɪ', 'e', 'ɛ', 'æ', 'ɑ', 'ɒ', 'ɔ', 'o', 'ʊ', 'u', 'ʌ', 'ə', 'ɜ']
  },
  { label: 'Diphthongs', symbols: ['eɪ', 'aɪ', 'ɔɪ', 'aʊ', 'oʊ', 'ɪə', 'eə', 'ʊə'] },
  {
    label: 'Consonants',
    symbols: [
      'p', 'b', 't', 'd', 'k', 'ɡ', 'tʃ', 'dʒ', 'f', 'v', 'θ', 'ð',
      's', 'z', 'ʃ', 'ʒ', 'h', 'm', 'n', 'ŋ', 'l', 'r', 'ɹ', 'j', 'w'
    ]
  }
];

export const TTS_PROVIDERS: SelectOption[] = [
  { value: 'pocket-tts', label: 'Pocket TTS' },
  { value: 'kokoro', label: 'Kokoro' }
];

export const BOOK_SOURCES: BookSourceOption[] = [
  { value: 'file', label: 'Ebook file (epub/azw3)', identifierPlaceholder: 'Path to the ebook file' },
  {
    value: 'ao3',
    label: 'AO3 work or series',
    identifierPlaceholder: 'Work id (e.g. 12345678) or series:<series-id>'
  },
  {
    value: 'ffnet',
    label: 'FanFiction.net story',
    identifierPlaceholder: 'Story id (e.g. 12345678) or story URL'
  },
  {
    value: 'extracted',
    label: 'Extracted text folder',
    identifierPlaceholder: 'Path to the extracted text folder'
  }
];
