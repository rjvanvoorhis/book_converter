import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';

import { PronunciationApiService } from '../../core/pronunciation-api.service';
import { DEFAULT_PRONUNCIATIONS_FOLDER, IPA_SYMBOL_GROUPS } from '../../core/constants';
import {
  PronunciationDictSummary,
  PronunciationEntry,
  PronunciationMethod
} from '../../core/models';

interface AliasRow {
  key: string;
  value: string;
}

@Component({
  selector: 'app-pronunciations',
  standalone: true,
  imports: [ReactiveFormsModule],
  templateUrl: './pronunciations.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './pronunciations.component.css'
})
export class PronunciationsComponent implements OnInit {
  private readonly formBuilder = inject(FormBuilder);
  private readonly api = inject(PronunciationApiService);

  readonly ipaGroups = IPA_SYMBOL_GROUPS;

  readonly folder = this.formBuilder.nonNullable.control(DEFAULT_PRONUNCIATIONS_FOLDER);
  readonly newDictName = this.formBuilder.nonNullable.control('');

  readonly dictionaries = signal<PronunciationDictSummary[]>([]);
  readonly dictionariesLoading = signal(false);
  readonly dictionariesError = signal<string | null>(null);

  readonly selectedPath = signal<string | null>(null);
  readonly method = signal<PronunciationMethod>('ipa');
  readonly aliases = signal<AliasRow[]>([]);
  readonly activeRowIndex = signal<number | null>(null);

  readonly loadError = signal<string | null>(null);
  readonly saving = signal(false);
  readonly saveError = signal<string | null>(null);
  readonly savedJustNow = signal(false);

  ngOnInit(): void {
    this.loadDictionaries();
  }

  loadDictionaries(): void {
    this.dictionariesLoading.set(true);
    this.dictionariesError.set(null);
    this.api.listDictionaries(this.folder.value).subscribe({
      next: (dictionaries) => {
        this.dictionariesLoading.set(false);
        this.dictionaries.set(dictionaries);
      },
      error: (err) => {
        this.dictionariesLoading.set(false);
        this.dictionariesError.set(_errorMessage(err));
      }
    });
  }

  startNewDictionary(): void {
    this.selectedPath.set(null);
    this.newDictName.setValue('');
    this.method.set('ipa');
    this.aliases.set([]);
    this.loadError.set(null);
    this.saveError.set(null);
    this.savedJustNow.set(false);
  }

  openDictionary(item: PronunciationDictSummary): void {
    this.selectedPath.set(item.path);
    this.loadError.set(null);
    this.saveError.set(null);
    this.savedJustNow.set(false);

    this.api.getDictionary(item.path).subscribe({
      next: (entries) => {
        const rows = Object.entries(entries).map(([key, entry]) => ({
          key,
          value: entry.value
        }));
        this.aliases.set(rows);
        const firstMethod = Object.values(entries)[0]?.method;
        this.method.set(firstMethod ?? 'ipa');
      },
      error: (err) => this.loadError.set(_errorMessage(err))
    });
  }

  isNewDictionary(): boolean {
    return this.selectedPath() === null;
  }

  currentPath(): string {
    const existing = this.selectedPath();
    if (existing) {
      return existing;
    }
    const name = this.newDictName.value.trim();
    return name ? `${this.folder.value}/${name}.json` : '';
  }

  setMethod(method: PronunciationMethod): void {
    this.method.set(method);
  }

  addAlias(): void {
    this.aliases.update((rows) => [...rows, { key: '', value: '' }]);
    this.activeRowIndex.set(this.aliases().length - 1);
  }

  removeAlias(index: number): void {
    this.aliases.update((rows) => rows.filter((_, i) => i !== index));
    if (this.activeRowIndex() === index) {
      this.activeRowIndex.set(null);
    }
  }

  setActiveRow(index: number): void {
    this.activeRowIndex.set(index);
  }

  updateKey(index: number, value: string): void {
    this.aliases.update((rows) =>
      rows.map((row, i) => (i === index ? { ...row, key: value } : row))
    );
  }

  updateValue(index: number, value: string): void {
    this.aliases.update((rows) =>
      rows.map((row, i) => (i === index ? { ...row, value } : row))
    );
  }

  insertSymbol(symbol: string): void {
    const index = this.activeRowIndex();
    if (index === null) {
      return;
    }
    const row = this.aliases()[index];
    this.updateValue(index, (row?.value ?? '') + symbol);
  }

  save(): void {
    const path = this.currentPath();
    if (!path) {
      this.saveError.set('Enter a name for the dictionary first.');
      return;
    }

    const method = this.method();
    const entries: Record<string, PronunciationEntry> = {};
    for (const row of this.aliases()) {
      const key = row.key.trim();
      if (!key) {
        continue;
      }
      entries[key] = { value: row.value, method };
    }

    this.saving.set(true);
    this.saveError.set(null);
    this.savedJustNow.set(false);

    this.api.saveDictionary(path, entries).subscribe({
      next: () => {
        this.saving.set(false);
        this.savedJustNow.set(true);
        this.selectedPath.set(path);
        this.loadDictionaries();
      },
      error: (err) => {
        this.saving.set(false);
        this.saveError.set(_errorMessage(err));
      }
    });
  }
}

function _errorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'error' in err) {
    const body = (err as { error?: unknown }).error;
    if (body && typeof body === 'object' && 'error' in body) {
      return String((body as { error?: unknown }).error);
    }
  }
  return 'Request failed. Is the API server running?';
}
