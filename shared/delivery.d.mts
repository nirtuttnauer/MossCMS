export class MossDeliveryError extends Error {
  code: string;
  requestId?: string;
  constructor(message: string, code?: string, requestId?: string);
}
export type DeliveryAsset = {
  id: string;
  mime: string;
  url: string;
  width: number | null;
  height: number | null;
  variants: Array<{ width: number; height: number; size: number; url: string }>;
};
export type DeliveryEntry<Data = Record<string, unknown>> = {
  id: string;
  typeKey: string;
  slug: string;
  publishedAt: string | null;
  data: Data;
  resolvedAssets: DeliveryAsset[];
};
export function createDeliveryClient(options: { baseUrl: string; token: string }): {
  query<Result>(document: string, variables?: Record<string, unknown>): Promise<Result>;
  pages<Data = Record<string, unknown>>(typeKey: string, first?: number): AsyncGenerator<DeliveryEntry<Data>[]>;
};
