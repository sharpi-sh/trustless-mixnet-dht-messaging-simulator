// Participant IDs from the Python configuration are sender-1…10 or receiver-1…10.
export function avatarUrl(deviceId: string): string {
  return `/avatars/${encodeURIComponent(deviceId)}.jpg`;
}
