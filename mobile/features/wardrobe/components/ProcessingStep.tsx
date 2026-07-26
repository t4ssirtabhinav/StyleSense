import { useEffect, useRef, useState } from 'react';
import { Button, Skeleton, Text } from '../../../components/ui';
import { SLOW_NETWORK_HINT_DELAY_MS } from '../wardrobe.constants';
import type { BatchItemStatus } from '../wardrobe.types';

export interface ProcessingStepProps {
  status: BatchItemStatus;
  /** Batch progress -- omit for a single-item flow. */
  currentIndex?: number;
  totalItems?: number;
  onRetry?: () => void;
  onSkip?: () => void;
}

const STATUS_TEXT: Partial<Record<BatchItemStatus, string>> = {
  uploading: 'Uploading your photo...',
  removing_bg: 'Removing background...',
  tagging: 'Analysing your item...',
};

const TIPS = [
  'Flat-lay or mannequin shots tag best.',
  'Good lighting helps us get colours right.',
  'One item per photo keeps tags accurate.',
];

// Skeleton shimmer + status text + rotating tip + slow-network hint + batch
// progress, per docs/tickets/SS-013-design.md's ProcessingStep spec.
export function ProcessingStep({
  status,
  currentIndex,
  totalItems,
  onRetry,
  onSkip,
}: ProcessingStepProps) {
  const [showSlowHint, setShowSlowHint] = useState(false);
  const [tipIndex, setTipIndex] = useState(0);
  const statusRef = useRef(status);

  // Timer resets per stage transition (upload -> bg-removal -> tagging),
  // not a single global 10s window -- each stage can independently be slow.
  useEffect(() => {
    statusRef.current = status;
    setShowSlowHint(false);
    const timer = setTimeout(() => {
      if (statusRef.current === status) {
        setShowSlowHint(true);
      }
    }, SLOW_NETWORK_HINT_DELAY_MS);
    return () => clearTimeout(timer);
  }, [status]);

  useEffect(() => {
    const interval = setInterval(() => {
      setTipIndex((current) => (current + 1) % TIPS.length);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  if (status === 'failed') {
    return (
      <>
        <Text variant="body">Something went wrong while processing.</Text>
        <Button
          variant="primary"
          accessibilityLabel="Retry"
          onPress={() => onRetry?.()}
        >
          Retry
        </Button>
        <Button
          variant="secondary"
          accessibilityLabel="Skip, tag manually"
          onPress={() => onSkip?.()}
        >
          Skip for now, tag manually
        </Button>
      </>
    );
  }

  return (
    <>
      <Skeleton variant="card" />
      <Text variant="heading" testID="processing-status-text">
        {STATUS_TEXT[status] ?? 'Processing...'}
      </Text>
      <Text variant="caption" testID="processing-tip">
        {TIPS[tipIndex]}
      </Text>
      {typeof currentIndex === 'number' && typeof totalItems === 'number' ? (
        <Text variant="caption" testID="batch-progress-text">
          {`${currentIndex + 1}/${totalItems}`}
        </Text>
      ) : null}
      {showSlowHint ? (
        <Text variant="caption" testID="slow-network-hint">
          This may take longer on slow connections
        </Text>
      ) : null}
    </>
  );
}
