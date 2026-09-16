import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, map } from 'rxjs';

import { environment } from '../../environments/environment';
import { OrganizationGroup } from './models';

@Injectable({ providedIn: 'root' })
export class OrganizationApiService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  listGroups(): Observable<OrganizationGroup[]> {
    return this.http
      .get<{ groups: OrganizationGroup[] }>(`${this.baseUrl}/organization/groups`)
      .pipe(map((response) => response.groups));
  }

  /** A series MUST be bound to a library/folder from the moment it exists -
   * there's no "create now, assign later" path. */
  createGroup(
    name: string,
    libraryId: string,
    folderId: string,
    isStandalone: boolean
  ): Observable<OrganizationGroup> {
    return this.http.post<OrganizationGroup>(`${this.baseUrl}/organization/groups`, {
      name,
      library_id: libraryId,
      folder_id: folderId,
      is_standalone: isStandalone
    });
  }

  renameGroup(groupId: string, name: string): Observable<OrganizationGroup> {
    return this.http.put<OrganizationGroup>(
      `${this.baseUrl}/organization/groups/${encodeURIComponent(groupId)}`,
      { name }
    );
  }

  deleteGroup(groupId: string): Observable<void> {
    return this.http.delete<void>(
      `${this.baseUrl}/organization/groups/${encodeURIComponent(groupId)}`
    );
  }

  addMember(
    groupId: string,
    path: string,
    sequence: number | null
  ): Observable<OrganizationGroup> {
    return this.http.post<OrganizationGroup>(
      `${this.baseUrl}/organization/groups/${encodeURIComponent(groupId)}/members`,
      { path, sequence }
    );
  }

  removeMember(groupId: string, path: string): Observable<OrganizationGroup> {
    const params = new HttpParams().set('path', path);
    return this.http.delete<OrganizationGroup>(
      `${this.baseUrl}/organization/groups/${encodeURIComponent(groupId)}/members`,
      { params }
    );
  }

  /** Resequences exactly the given paths to 1..N in the given order - any
   * other member (e.g. an unordered side story) keeps its sequence as-is. */
  reorderMembers(groupId: string, orderedPaths: string[]): Observable<OrganizationGroup> {
    return this.http.post<OrganizationGroup>(
      `${this.baseUrl}/organization/groups/${encodeURIComponent(groupId)}/reorder`,
      { paths: orderedPaths }
    );
  }

  /** Staged works (from data/audiobooks) not yet assigned to any group. */
  listUnassigned(audiobookFolder: string): Observable<string[]> {
    const params = new HttpParams().set('audiobook_folder', audiobookFolder);
    return this.http
      .get<{ paths: string[] }>(`${this.baseUrl}/organization/unassigned`, { params })
      .pipe(map((response) => response.paths));
  }
}
