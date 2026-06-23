import type { Figure } from "@/lib/api"

/**
 * A figure can be enlarged in the lightbox only when it has a real, available image.
 * Placeholder figures (no `image_url` or `image_available` false) have nothing to zoom,
 * so they get no click affordance. Pure + deterministic — unit-tested, no React import.
 */
export function figureIsEnlargeable(
  fig: Pick<Figure, "image_url" | "image_available">,
): boolean {
  return Boolean(fig.image_url) && fig.image_available
}
