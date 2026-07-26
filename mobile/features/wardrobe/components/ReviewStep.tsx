import { Image } from 'expo-image';
import { useEffect, useState } from 'react';
import { Badge, Button, Card, Input, Text } from '../../../components/ui';
import {
  LOW_CONFIDENCE_THRESHOLD,
  OCCASION_BADGE_COLOR_MAP,
  OCCASION_TYPES,
  SEASON_TAGS,
} from '../wardrobe.constants';
import { useSaveWardrobeItemTags } from '../wardrobe.queries';
import { fetchWardrobeItemImageUrl } from '../wardrobe.service';
import type {
  GarmentTagsDraft,
  OccasionType,
  SeasonTag,
  WardrobeCategory,
  WardrobeItemProcessingStatus,
} from '../wardrobe.types';

export interface ReviewStepProps {
  itemId: string;
  jwt: string;
  processingStatus: WardrobeItemProcessingStatus;
  initialTags: GarmentTagsDraft;
  onOpenCategoryPicker: () => void;
  /** Set by the parent screen after CategoryPicker's onSelect fires. */
  selectedCategoryOverride?: WardrobeCategory;
  onSaved: (tags: GarmentTagsDraft) => void;
}

function contentFlagMessage(
  flag: GarmentTagsDraft['contentFlag'],
): string | null {
  if (flag === 'not_clothing') return "Doesn't look like clothing";
  if (flag === 'nsfw' || flag === 'other') {
    return "Couldn't process this image. Please try a different photo.";
  }
  return null;
}

function toggleInArray<T>(list: T[], value: T): T[] {
  return list.includes(value)
    ? list.filter((item) => item !== value)
    : [...list, value];
}

// Editable cutout review -- BG-removed image, editable Badge/Input chips,
// low-confidence/moderation banners, alternatives picker, "Looks Good!"
// save. Per docs/tickets/SS-013-design.md's ReviewStep spec.
export function ReviewStep({
  itemId,
  jwt,
  processingStatus,
  initialTags,
  onOpenCategoryPicker,
  selectedCategoryOverride,
  onSaved,
}: ReviewStepProps) {
  const [draft, setDraft] = useState<GarmentTagsDraft>(initialTags);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageSource, setImageSource] = useState<'clean' | 'original' | null>(
    null,
  );
  const saveMutation = useSaveWardrobeItemTags();

  useEffect(() => {
    let cancelled = false;
    fetchWardrobeItemImageUrl(itemId, jwt)
      .then((result) => {
        if (!cancelled) {
          setImageUrl(result.url);
          setImageSource(result.source);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setImageUrl(null);
          setImageSource(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [itemId, jwt]);

  useEffect(() => {
    if (selectedCategoryOverride) {
      setDraft((current) => ({
        ...current,
        category: selectedCategoryOverride,
      }));
    }
  }, [selectedCategoryOverride]);

  const toggleOccasion = (occasion: OccasionType) => {
    setDraft((current) => ({
      ...current,
      occasionTags: toggleInArray(current.occasionTags, occasion),
    }));
  };

  const toggleSeason = (season: SeasonTag) => {
    setDraft((current) => ({
      ...current,
      seasonTags: toggleInArray(current.seasonTags, season),
    }));
  };

  const handleSelectAlternative = (category: WardrobeCategory) => {
    setDraft((current) => ({ ...current, category }));
  };

  const handleLooksGood = () => {
    saveMutation.mutate(
      { itemId, tags: draft },
      { onSuccess: () => onSaved(draft) },
    );
  };

  const showFallbackNote =
    processingStatus !== 'bg_removed' && imageSource === 'original';
  const showLowConfidence = draft.confidence < LOW_CONFIDENCE_THRESHOLD;
  const flagMessage = contentFlagMessage(draft.contentFlag);

  return (
    <Card testID="review-step">
      {imageUrl ? (
        <Image
          testID="review-image"
          source={{ uri: imageUrl }}
          style={{ width: '100%', height: 300 }}
          contentFit="contain"
          accessibilityLabel="Item photo"
        />
      ) : null}
      {showFallbackNote ? (
        <Text variant="caption" testID="bg-fallback-note">
          Background not removed
        </Text>
      ) : null}

      {showLowConfidence ? (
        <Text variant="caption" testID="low-confidence-banner">
          We're not fully sure about these tags -- please double check them.
        </Text>
      ) : null}
      {flagMessage ? (
        <Text variant="caption" testID="content-flag-banner">
          {flagMessage}
        </Text>
      ) : null}
      {draft.containsPerson ? (
        <Text variant="caption" testID="contains-person-nudge">
          Try a flat-lay or mannequin shot for best results
        </Text>
      ) : null}

      <Button
        variant="secondary"
        accessibilityLabel="Choose category"
        onPress={onOpenCategoryPicker}
      >
        {draft.category ?? 'Choose category'}
      </Button>

      <Input
        variant="text"
        label="Subcategory"
        value={draft.subcategory ?? ''}
        onChangeText={(text) =>
          setDraft((current) => ({ ...current, subcategory: text }))
        }
      />
      <Input
        variant="text"
        label="Primary colour"
        value={draft.colorPrimary ?? ''}
        onChangeText={(text) =>
          setDraft((current) => ({ ...current, colorPrimary: text }))
        }
      />
      <Input
        variant="text"
        label="Secondary colour"
        value={draft.colorSecondary ?? ''}
        onChangeText={(text) =>
          setDraft((current) => ({ ...current, colorSecondary: text }))
        }
      />
      <Input
        variant="text"
        label="Pattern"
        value={draft.pattern ?? ''}
        onChangeText={(text) =>
          setDraft((current) => ({ ...current, pattern: text }))
        }
      />
      <Input
        variant="text"
        label="Fabric"
        value={draft.fabric ?? ''}
        onChangeText={(text) =>
          setDraft((current) => ({ ...current, fabric: text }))
        }
      />

      {OCCASION_TYPES.map((occasion) => (
        <Badge
          key={occasion}
          testID={`occasion-badge-${occasion}`}
          label={occasion}
          occasion={OCCASION_BADGE_COLOR_MAP[occasion]}
          selected={draft.occasionTags.includes(occasion)}
          onPress={() => toggleOccasion(occasion)}
        />
      ))}

      {SEASON_TAGS.map((season) => (
        <Badge
          key={season}
          testID={`season-badge-${season}`}
          label={season}
          selected={draft.seasonTags.includes(season)}
          onPress={() => toggleSeason(season)}
        />
      ))}

      {draft.alternatives && draft.alternatives.length > 0 ? (
        <>
          <Text variant="caption">Did you mean:</Text>
          {draft.alternatives.map((alternative) => (
            <Badge
              key={alternative}
              testID={`alternative-badge-${alternative}`}
              label={alternative}
              onPress={() => handleSelectAlternative(alternative)}
            />
          ))}
        </>
      ) : null}

      <Button
        variant="primary"
        accessibilityLabel="Looks Good!"
        loading={saveMutation.isPending}
        onPress={handleLooksGood}
      >
        Looks Good!
      </Button>
    </Card>
  );
}
