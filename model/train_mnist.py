# model/train_mnist.py
import os
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms

# 1.Reproducibility
torch.manual_seed(42)

# 2.Define the exact hardware-targeted architecture
class SysMAC8Model(nn.Module):
    def __init__(self):
        super(SysMAC8Model, self).__init__()
        #Flatten 28x28 image to 784 pixels
        self.flatten = nn.Flatten()
        
        #Layer 1:784 -> 32 neurons. Bias included explicitly for accumulator init.
        self.fc1 = nn.Linear(784, 32, bias=True)
        
        #Hardware ReLU matching our requantizer logic
        self.relu = nn.ReLU()
        
        # Layer 2:32 -> 10 output classes.
        self.fc2 = nn.Linear(32, 10, bias=True)

    def forward(self, x):
        x = self.flatten(x)
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2(x)
        return x

def train():
    print("Downloading and preparing MNIST dataset...")
    #Standard normalization: converting [0, 255] pixel values to [0.0, 1.0] tensors
    transform = transforms.ToTensor()
    
    # Create data/ directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    
    train_dataset = datasets.MNIST(root='./data', train=True, download=True, transform=transform)
    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=64, shuffle=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = SysMAC8Model().to(device)
    
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    epochs = 3
    print(f"Starting training on {device} for {epochs} epochs...")
    
    model.train()
    for epoch in range(epochs):
        running_loss = 0.0
        correct = 0
        total = 0
        
        for batch_idx, (data, target) in enumerate(train_loader):
            data, target = data.to(device), target.to(device)
            
            optimizer.zero_grad()
            outputs = model(data)
            loss = criterion(outputs, target)
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
            _, predicted = outputs.max(1)
            total += target.size(0)
            correct += predicted.eq(target).sum().item()
            
            if batch_idx % 200 == 0:
                print(f"Epoch [{epoch+1}/{epochs}] Batch [{batch_idx}/{len(train_loader)}] Loss: {loss.item():.4f} Acc: {100.*correct/total:.2f}%")

    print("Training complete.")
    
    #3.Save the floating-point artifacts for quantize.py to inspect
    torch.save(model.state_dict(), "model.pth")
    print("Raw FP32 model saved to 'model.pth'.")

if __name__ == "__main__":
    train()