import { RandomForestClassifier } from "ml-random-forest";
import type { Side } from "@ta/shared";

const LABELS: Side[] = ["BUY", "SELL", "NO_TRADE"];

/** Train a small RF on synthetic feature rows; replace with historical CSV in production. */
export function trainSignalForest(): RandomForestClassifier {
  const training: number[][] = [];
  const targets: number[] = [];

  for (let i = 0; i < 400; i++) {
    const rsiF = 20 + Math.random() * 60;
    const emaSpread = (Math.random() - 0.5) * 0.02;
    const volRatio = 0.5 + Math.random() * 1.5;
    const pcr = 0.5 + Math.random();
    training.push([rsiF, emaSpread, volRatio, pcr]);

    let y = 2;
    if (rsiF > 55 && emaSpread > 0 && volRatio > 1) y = 0;
    else if (rsiF < 45 && emaSpread < 0 && volRatio > 1) y = 1;
    targets.push(y);
  }

  const rf = new RandomForestClassifier({
    seed: 42,
    maxFeatures: 2,
    replacement: true,
    nEstimators: 25,
    treeOptions: { maxDepth: 8, minNumSamples: 3 },
    useSampleBagging: false,
    noOOB: true,
    isClassifier: true,
  });
  rf.train(training, targets);
  return rf;
}

export function predictSide(
  model: RandomForestClassifier,
  features: number[],
): { label: Side; score: number } {
  const row = [features];
  const pred = model.predict(row)[0] as number;
  const label = LABELS[pred] ?? "NO_TRADE";
  const probs = [0, 1, 2].map((lab) => model.predictProbability(row, lab)[0] ?? 0);
  const score = Math.round(Math.max(...probs) * 100);
  return { label, score };
}
